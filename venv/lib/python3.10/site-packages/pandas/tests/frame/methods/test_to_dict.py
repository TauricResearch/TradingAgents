from collections import (
    OrderedDict,
    defaultdict,
)
from datetime import datetime

import numpy as np
import pytest
import pytz

from pandas import (
    NA,
    DataFrame,
    Index,
    Interval,
    MultiIndex,
    Period,
    Series,
    Timedelta,
    Timestamp,
)
import pandas._testing as tm


class TestDataFrameToDict:
    def test_to_dict_timestamp(self):
        # GH#11247
        # split/records producing np.datetime64 rather than Timestamps
        # on datetime64[ns] dtypes only

        tsmp = Timestamp("20130101")
        test_data = DataFrame({"A": [tsmp, tsmp], "B": [tsmp, tsmp]})
        test_data_mixed = DataFrame({"A": [tsmp, tsmp], "B": [1, 2]})

        expected_records = [{"A": tsmp, "B": tsmp}, {"A": tsmp, "B": tsmp}]
        expected_records_mixed = [{"A": tsmp, "B": 1}, {"A": tsmp, "B": 2}]

        assert test_data.to_dict(orient="records") == expected_records
        assert test_data_mixed.to_dict(orient="records") == expected_records_mixed

        expected_series = {
            "A": Series([tsmp, tsmp], name="A"),
            "B": Series([tsmp, tsmp], name="B"),
        }
        expected_series_mixed = {
            "A": Series([tsmp, tsmp], name="A"),
            "B": Series([1, 2], name="B"),
        }

        tm.assert_dict_equal(test_data.to_dict(orient="series"), expected_series)
        tm.assert_dict_equal(
            test_data_mixed.to_dict(orient="series"), expected_series_mixed
        )

        expected_split = {
            "index": [0, 1],
            "data": [[tsmp, tsmp], [tsmp, tsmp]],
            "columns": ["A", "B"],
        }
        expected_split_mixed = {
            "index": [0, 1],
            "data": [[tsmp, 1], [tsmp, 2]],
            "columns": ["A", "B"],
        }

        tm.assert_dict_equal(test_data.to_dict(orient="split"), expected_split)
        tm.assert_dict_equal(
            test_data_mixed.to_dict(orient="split"), expected_split_mixed
        )

    def test_to_dict_index_not_unique_with_index_orient(self):
        # GH#22801
        # Data loss when indexes are not unique. Raise ValueError.
        df = DataFrame({"a": [1, 2], "b": [0.5, 0.75]}, index=["A", "A"])
        msg = "DataFrame index must be unique for orient='index'"
        with pytest.raises(ValueError, match=msg):
            df.to_dict(orient="index")

    def test_to_dict_invalid_orient(self):
        df = DataFrame({"A": [0, 1]})
        msg = "orient 'xinvalid' not understood"
        with pytest.raises(ValueError, match=msg):
            df.to_dict(orient="xinvalid")

    @pytest.mark.parametrize("orient", ["d", "l", "r", "sp", "s", "i"])
    def test_to_dict_short_orient_raises(self, orient):
        # GH#32515
        df = DataFrame({"A": [0, 1]})
        with pytest.raises(ValueError, match="not understood"):
            df.to_dict(orient=orient)

    @pytest.mark.parametrize("mapping", [dict, defaultdict(list), OrderedDict])
    def test_to_dict(self, mapping):
        # orient= should only take the listed options
        # see GH#32515
        test_data = {"A": {"1": 1, "2": 2}, "B": {"1": "1", "2": "2", "3": "3"}}

        # GH#16122
        recons_data = DataFrame(test_data).to_dict(into=mapping)

        for k, v in test_data.items():
            for k2, v2 in v.items():
                assert v2 == recons_data[k][k2]

        recons_data = DataFrame(test_data).to_dict("list", into=mapping)

        for k, v in test_data.items():
            for k2, v2 in v.items():
                assert v2 == recons_data[k][int(k2) - 1]

        recons_data = DataFrame(test_data).to_dict("series", into=mapping)

        for k, v in test_data.items():
            for k2, v2 in v.items():
                assert v2 == recons_data[k][k2]

        recons_data = DataFrame(test_data).to_dict("split", into=mapping)
        expected_split = {
            "columns": ["A", "B"],
            "index": ["1", "2", "3"],
            "data": [[1.0, "1"], [2.0, "2"], [np.nan, "3"]],
        }
        tm.assert_dict_equal(recons_data, expected_split)

        recons_data = DataFrame(test_data).to_dict("records", into=mapping)
        expected_records = [
            {"A": 1.0, "B": "1"},
            {"A": 2.0, "B": "2"},
            {"A": np.nan, "B": "3"},
        ]
        assert isinstance(recons_data, list)
        assert len(recons_data) == 3
        for left, right in zip(recons_data, expected_records):
            tm.assert_dict_equal(left, right)

        # GH#10844
        recons_data = DataFrame(test_data).to_dict("index")

        for k, v in test_data.items():
            for k2, v2 in v.items():
                assert v2 == recons_data[k2][k]

        df = DataFrame(test_data)
        df["duped"] = df[df.columns[0]]
        recons_data = df.to_dict("index")
        comp_data = test_data.copy()
        comp_data["duped"] = comp_data[df.columns[0]]
        for k, v in comp_data.items():
            for k2, v2 in v.items():
                assert v2 == recons_data[k2][k]

    @pytest.mark.parametrize("mapping", [list, defaultdict, []])
    def test_to_dict_errors(self, mapping):
        # GH#16122
        df = DataFrame(np.random.default_rng(2).standard_normal((3, 3)))
        msg = "|".join(
            [
                "unsupported type: <class 'list'>",
                r"to_dict\(\) only accepts initialized defaultdicts",
            ]
        )
        with pytest.raises(TypeError, match=msg):
            df.to_dict(into=mapping)

    def test_to_dict_not_unique_warning(self):
        # GH#16927: When converting to a dict, if a column has a non-unique name
        # it will be dropped, throwing a warning.
        df = DataFrame([[1, 2, 3]], columns=["a", "a", "b"])
        with tm.assert_produces_warning(UserWarning):
            df.to_dict()

    @pytest.mark.filterwarnings("ignore::UserWarning")
    @pytest.mark.parametrize(
        "orient,expected",
        [
            ("list", {"A": [2, 5], "B": [3, 6]}),
            ("dict", {"A": {0: 2, 1: 5}, "B": {0: 3, 1: 6}}),
        ],
    )
    def test_to_dict_not_unique(self, orient, expected):
        # GH#54824: This is to make sure that dataframes with non-unique column
        # would have uniform behavior throughout different orients
        df = DataFrame([[1, 2, 3], [4, 5, 6]], columns=["A", "A", "B"])
        result = df.to_dict(orient)
        assert result == expected

    # orient - orient argument to to_dict function
    # item_getter - function for extracting value from
    # the resulting dict using column name and index
    @pytest.mark.parametrize(
        "orient,item_getter",
        [
            ("dict", lambda d, col, idx: d[col][idx]),
            ("records", lambda d, col, idx: d[idx][col]),
            ("list", lambda d, col, idx: d[col][idx]),
            ("split", lambda d, col, idx: d["data"][idx][d["columns"].index(col)]),
            ("index", lambda d, col, idx: d[idx][col]),
        ],
    )
    def test_to_dict_box_scalars(self, orient, item_getter):
        # GH#14216, GH#23753
        # make sure that we are boxing properly
        df = DataFrame({"a": [1, 2], "b": [0.1, 0.2]})
        result = df.to_dict(orient=orient)
        assert isinstance(item_getter(result, "a", 0), int)
        assert isinstance(item_getter(result, "b", 0), float)

    def test_to_dict_tz(self):
        # GH#18372 When converting to dict with orient='records' columns of
        # datetime that are tz-aware were not converted to required arrays
        data = [
            (datetime(2017, 11, 18, 21, 53, 0, 219225, tzinfo=pytz.utc),),
            (datetime(2017, 11, 18, 22, 6, 30, 61810, tzinfo=pytz.utc),),
        ]
        df = DataFrame(list(data), columns=["d"])

        result = df.to_dict(orient="records")
        expected = [
            {"d": Timestamp("2017-11-18 21:53:00.219225+0000", tz=pytz.utc)},
            {"d": Timestamp("2017-11-18 22:06:30.061810+0000", tz=pytz.utc)},
        ]
        tm.assert_dict_equal(result[0], expected[0])
        tm.assert_dict_equal(result[1], expected[1])

    @pytest.mark.parametrize(
        "into, expected",
        [
            (
                dict,
                {
                    0: {"int_col": 1, "float_col": 1.0},
                    1: {"int_col": 2, "float_col": 2.0},
                    2: {"int_col": 3, "float_col": 3.0},
                },
            ),
            (
                OrderedDict,
                OrderedDict(
                    [
                        (0, {"int_col": 1, "float_col": 1.0}),
                        (1, {"int_col": 2, "float_col": 2.0}),
                        (2, {"int_col": 3, "float_col": 3.0}),
                    ]
                ),
            ),
            (
                defaultdict(dict),
                defaultdict(
                    dict,
                    {
                        0: {"int_col": 1, "float_col": 1.0},
                        1: {"int_col": 2, "float_col": 2.0},
                        2: {"int_col": 3, "float_col": 3.0},
                    },
                ),
            ),
        ],
    )
    def test_to_dict_index_dtypes(self, into, expected):
        # GH#18580
        # When using to_dict(orient='index') on a dataframe with int
        # and float columns only the int columns were cast to float

        df = DataFrame({"int_col": [1, 2, 3], "float_col": [1.0, 2.0, 3.0]})

        result = df.to_dict(orient="index", into=into)
        cols = ["int_col", "float_col"]
        result = DataFrame.from_dict(result, orient="index")[cols]
        expected = DataFrame.from_dict(expected, orient="index")[cols]
        tm.assert_frame_equal(result, expected)

    def test_to_dict_numeric_names(self):
        # GH#24940
        df = DataFrame({str(i): [i] for i in range(5)})
        result = set(df.to_dict("records")[0].keys())
        expected = set(df.columns)
        assert result == expected

    def test_to_dict_wide(self):
        # GH#24939
        df = DataFrame({(f"A_{i:d}"): [i] for i in range(256)})
        result = df.to_dict("records")[0]
        expected = {f"A_{i:d}": i for i in range(256)}
        assert result == expected

    @pytest.mark.parametrize(
        "data,dtype",
        (
            ([True, True, False], bool),
            [
                [
                    datetime(2018, 1, 1),
                    datetime(2019, 2, 2),
                    datetime(2020, 3, 3),
                ],
                Timestamp,
            ],
            [[1.0, 2.0, 3.0], float],
            [[1, 2, 3], int],
            [["X", "Y", "Z"], str],
        ),
    )
    def test_to_dict_orient_dtype(self, data, dtype):
        # GH22620 & GH21256

        df = DataFrame({"a": data})
        d = df.to_dict(orient="records")
        assert all(type(record["a"]) is dtype for record in d)

    @pytest.mark.parametrize(
        "data,expected_dtype",
        (
            [np.uint64(2), int],
            [np.int64(-9), int],
            [np.float64(1.1), float],
            [np.bool_(True), bool],
            [np.datetime64("2005-02-25"), Timestamp],
        ),
    )
    def test_to_dict_scalar_constructor_orient_dtype(self, data, expected_dtype):
        # GH22620 & GH21256

        df = DataFrame({"a": data}, index=[0])
        d = df.to_dict(orient="records")
        result = type(d[0]["a"])
        assert result is expected_dtype

    def test_to_dict_mixed_numeric_frame(self):
        # GH 12859
        df = DataFrame({"a": [1.0], "b": [9.0]})
        result = df.reset_index().to_dict("records")
        expected = [{"index": 0, "a": 1.0, "b": 9.0}]
        assert result == expected

    @pytest.mark.parametrize(
        "index",
        [
            None,
            Index(["aa", "bb"]),
            Index(["aa", "bb"], name="cc"),
            MultiIndex.from_tuples([("a", "b"), ("a", "c")]),
            MultiIndex.from_tuples([("a", "b"), ("a", "c")], names=["n1", "n2"]),
        ],
    )
    @pytest.mark.parametrize(
        "columns",
        [
            ["x", "y"],
            Index(["x", "y"]),
            Index(["x", "y"], name="z"),
            MultiIndex.from_tuples([("x", 1), ("y", 2)]),
            MultiIndex.from_tuples([("x", 1), ("y", 2)], names=["z1", "z2"]),
        ],
    )
    def test_to_dict_orient_tight(self, index, columns):
        df = DataFrame.from_records(
            [[1, 3], [2, 4]],
            columns=columns,
            index=index,
        )
        roundtrip = DataFrame.from_dict(df.to_dict(orient="tight"), orient="tight")

        tm.assert_frame_equal(df, roundtrip)

    @pytest.mark.parametrize(
        "orient",
        ["dict", "list", "split", "records", "index", "tight"],
    )
    @pytest.mark.parametrize(
        "data,expected_types",
        (
            (
                {
                    "a": [np.int64(1), 1, np.int64(3)],
                    "b": [np.float64(1.0), 2.0, np.float64(3.0)],
                    "c": [np.float64(1.0), 2, np.int64(3)],
                    "d": [np.float64(1.0), "a", np.int64(3)],
                    "e": [np.float64(1.0), ["a"], np.int64(3)],
                    "f": [np.float64(1.0), ("a",), np.int64(3)],
                },
                {
                    "a": [int, int, int],
                    "b": [float, float, float],
                    "c": [float, float, float],
                    "d": [float, str, int],
                    "e": [float, list, int],
                    "f": [float, tuple, int],
                },
            ),
            (
                {
                    "a": [1, 2, 3],
                    "b": [1.1, 2.2, 3.3],
                },
                {
                    "a": [int, int, int],
                    "b": [float, float, float],
                },
            ),
            (  # Make sure we have one df which is all object type cols
                {
                    "a": [1, "hello", 3],
                    "b": [1.1, "world", 3.3],
                },
                {
                    "a": [int, str, int],
                    "b": [float, str, float],
                },
            ),
        ),
    )
    def test_to_dict_returns_native_types(self, orient, data, expected_types):
        # GH 46751
        # Tests we get back native types for all orient types
        df = DataFrame(data)
        result = df.to_dict(orient)
        if orient == "dict":
            assertion_iterator = (
                (i, key, value)
                for key, index_value_map in result.items()
                for i, value in index_value_map.items()
            )
        elif orient == "list":
            assertion_iterator = (
                (i, key, value)
                for key, values in result.items()
                for i, value in enumerate(values)
            )
        elif orient in {"split", "tight"}:
            assertion_iterator = (
                (i, key, result["data"][i][j])
                for i in result["index"]
                for j, key in enumerate(result["columns"])
            )
        elif orient == "records":
            assertion_iterator = (
                (i, key, value)
                for i, record in enumerate(result)
                for key, value in record.items()
            )
        elif orient == "index":
            assertion_iterator = (
                (i, key, value)
                for i, record in result.items()
                for key, value in record.items()
            )

        for i, key, value in assertion_iterator:
            assert value == data[key][i]
            assert type(value) is expected_types[key][i]

    @pytest.mark.parametrize("orient", ["dict", "list", "series", "records", "index"])
    def test_to_dict_index_false_error(self, orient):
        # GH#46398
        df = DataFrame({"col1": [1, 2], "col2": [3, 4]}, index=["row1", "row2"])
        msg = "'index=False' is only valid when 'orient' is 'split' or 'tight'"
        with pytest.raises(ValueError, match=msg):
            df.to_dict(orient=orient, index=False)

    @pytest.mark.parametrize(
        "orient, expected",
        [
            ("split", {"columns": ["col1", "col2"], "data": [[1, 3], [2, 4]]}),
            (
                "tight",
                {
                    "columns": ["col1", "col2"],
                    "data": [[1, 3], [2, 4]],
                    "column_names": [None],
                },
            ),
        ],
    )
    def test_to_dict_index_false(self, orient, expected):
        # GH#46398
        df = DataFrame({"col1": [1, 2], "col2": [3, 4]}, index=["row1", "row2"])
        result = df.to_dict(orient=orient, index=False)
        tm.assert_dict_equal(result, expected)

    @pytest.mark.parametrize(
        "orient, expected",
        [
            ("dict", {"a": {0: 1, 1: None}}),
            ("list", {"a": [1, None]}),
            ("split", {"index": [0, 1], "columns": ["a"], "data": [[1], [None]]}),
            (
                "tight",
                {
                    "index": [0, 1],
                    "columns": ["a"],
                    "data": [[1], [None]],
                    "index_names": [None],
                    "column_names": [None],
                },
            ),
            ("records", [{"a": 1}, {"a": None}]),
            ("index", {0: {"a": 1}, 1: {"a": None}}),
        ],
    )
    def test_to_dict_na_to_none(self, orient, expected):
        # GH#50795
        df = DataFrame({"a": [1, NA]}, dtype="Int64")
        result = df.to_dict(orient=orient)
        assert result == expected

    def test_to_dict_masked_native_python(self):
        # GH#34665
        df = DataFrame({"a": Series([1, 2], dtype="Int64"), "B": 1})
        result = df.to_dict(orient="records")
        assert isinstance(result[0]["a"], int)

        df = DataFrame({"a": Series([1, NA], dtype="Int64"), "B": 1})
        result = df.to_dict(orient="records")
        assert isinstance(result[0]["a"], int)

    def test_to_dict_pos_args_deprecation(self):
        # GH-54229
        df = DataFrame({"a": [1, 2, 3]})
        msg = (
            r"Starting with pandas version 3.0 all arguments of to_dict except for the "
            r"argument 'orient' will be keyword-only."
        )
        with tm.assert_produces_warning(FutureWarning, match=msg):
            df.to_dict("records", {})


@pytest.mark.parametrize(
    "val", [Timestamp(2020, 1, 1), Timedelta(1), Period("2020"), Interval(1, 2)]
)
def test_to_dict_list_pd_scalars(val):
    # GH 54824
    df = DataFrame({"a": [val]})
    result = df.to_dict(orient="list")
    expected = {"a": [val]}
    assert result == expected
