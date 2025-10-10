import re

import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    date_range,
    lreshape,
    melt,
    wide_to_long,
)
import pandas._testing as tm


@pytest.fixture
def df():
    res = DataFrame(
        np.random.default_rng(2).standard_normal((10, 4)),
        columns=Index(list("ABCD")),
        index=date_range("2000-01-01", periods=10, freq="B"),
    )
    res["id1"] = (res["A"] > 0).astype(np.int64)
    res["id2"] = (res["B"] > 0).astype(np.int64)
    return res


@pytest.fixture
def df1():
    res = DataFrame(
        [
            [1.067683, -1.110463, 0.20867],
            [-1.321405, 0.368915, -1.055342],
            [-0.807333, 0.08298, -0.873361],
        ]
    )
    res.columns = [list("ABC"), list("abc")]
    res.columns.names = ["CAP", "low"]
    return res


@pytest.fixture
def var_name():
    return "var"


@pytest.fixture
def value_name():
    return "val"


class TestMelt:
    def test_top_level_method(self, df):
        result = melt(df)
        assert result.columns.tolist() == ["variable", "value"]

    def test_method_signatures(self, df, df1, var_name, value_name):
        tm.assert_frame_equal(df.melt(), melt(df))

        tm.assert_frame_equal(
            df.melt(id_vars=["id1", "id2"], value_vars=["A", "B"]),
            melt(df, id_vars=["id1", "id2"], value_vars=["A", "B"]),
        )

        tm.assert_frame_equal(
            df.melt(var_name=var_name, value_name=value_name),
            melt(df, var_name=var_name, value_name=value_name),
        )

        tm.assert_frame_equal(df1.melt(col_level=0), melt(df1, col_level=0))

    def test_default_col_names(self, df):
        result = df.melt()
        assert result.columns.tolist() == ["variable", "value"]

        result1 = df.melt(id_vars=["id1"])
        assert result1.columns.tolist() == ["id1", "variable", "value"]

        result2 = df.melt(id_vars=["id1", "id2"])
        assert result2.columns.tolist() == ["id1", "id2", "variable", "value"]

    def test_value_vars(self, df):
        result3 = df.melt(id_vars=["id1", "id2"], value_vars="A")
        assert len(result3) == 10

        result4 = df.melt(id_vars=["id1", "id2"], value_vars=["A", "B"])
        expected4 = DataFrame(
            {
                "id1": df["id1"].tolist() * 2,
                "id2": df["id2"].tolist() * 2,
                "variable": ["A"] * 10 + ["B"] * 10,
                "value": (df["A"].tolist() + df["B"].tolist()),
            },
            columns=["id1", "id2", "variable", "value"],
        )
        tm.assert_frame_equal(result4, expected4)

    @pytest.mark.parametrize("type_", (tuple, list, np.array))
    def test_value_vars_types(self, type_, df):
        # GH 15348
        expected = DataFrame(
            {
                "id1": df["id1"].tolist() * 2,
                "id2": df["id2"].tolist() * 2,
                "variable": ["A"] * 10 + ["B"] * 10,
                "value": (df["A"].tolist() + df["B"].tolist()),
            },
            columns=["id1", "id2", "variable", "value"],
        )
        result = df.melt(id_vars=["id1", "id2"], value_vars=type_(("A", "B")))
        tm.assert_frame_equal(result, expected)

    def test_vars_work_with_multiindex(self, df1):
        expected = DataFrame(
            {
                ("A", "a"): df1[("A", "a")],
                "CAP": ["B"] * len(df1),
                "low": ["b"] * len(df1),
                "value": df1[("B", "b")],
            },
            columns=[("A", "a"), "CAP", "low", "value"],
        )

        result = df1.melt(id_vars=[("A", "a")], value_vars=[("B", "b")])
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "id_vars, value_vars, col_level, expected",
        [
            (
                ["A"],
                ["B"],
                0,
                DataFrame(
                    {
                        "A": {0: 1.067683, 1: -1.321405, 2: -0.807333},
                        "CAP": {0: "B", 1: "B", 2: "B"},
                        "value": {0: -1.110463, 1: 0.368915, 2: 0.08298},
                    }
                ),
            ),
            (
                ["a"],
                ["b"],
                1,
                DataFrame(
                    {
                        "a": {0: 1.067683, 1: -1.321405, 2: -0.807333},
                        "low": {0: "b", 1: "b", 2: "b"},
                        "value": {0: -1.110463, 1: 0.368915, 2: 0.08298},
                    }
                ),
            ),
        ],
    )
    def test_single_vars_work_with_multiindex(
        self, id_vars, value_vars, col_level, expected, df1
    ):
        result = df1.melt(id_vars, value_vars, col_level=col_level)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "id_vars, value_vars",
        [
            [("A", "a"), [("B", "b")]],
            [[("A", "a")], ("B", "b")],
            [("A", "a"), ("B", "b")],
        ],
    )
    def test_tuple_vars_fail_with_multiindex(self, id_vars, value_vars, df1):
        # melt should fail with an informative error message if
        # the columns have a MultiIndex and a tuple is passed
        # for id_vars or value_vars.
        msg = r"(id|value)_vars must be a list of tuples when columns are a MultiIndex"
        with pytest.raises(ValueError, match=msg):
            df1.melt(id_vars=id_vars, value_vars=value_vars)

    def test_custom_var_name(self, df, var_name):
        result5 = df.melt(var_name=var_name)
        assert result5.columns.tolist() == ["var", "value"]

        result6 = df.melt(id_vars=["id1"], var_name=var_name)
        assert result6.columns.tolist() == ["id1", "var", "value"]

        result7 = df.melt(id_vars=["id1", "id2"], var_name=var_name)
        assert result7.columns.tolist() == ["id1", "id2", "var", "value"]

        result8 = df.melt(id_vars=["id1", "id2"], value_vars="A", var_name=var_name)
        assert result8.columns.tolist() == ["id1", "id2", "var", "value"]

        result9 = df.melt(
            id_vars=["id1", "id2"], value_vars=["A", "B"], var_name=var_name
        )
        expected9 = DataFrame(
            {
                "id1": df["id1"].tolist() * 2,
                "id2": df["id2"].tolist() * 2,
                var_name: ["A"] * 10 + ["B"] * 10,
                "value": (df["A"].tolist() + df["B"].tolist()),
            },
            columns=["id1", "id2", var_name, "value"],
        )
        tm.assert_frame_equal(result9, expected9)

    def test_custom_value_name(self, df, value_name):
        result10 = df.melt(value_name=value_name)
        assert result10.columns.tolist() == ["variable", "val"]

        result11 = df.melt(id_vars=["id1"], value_name=value_name)
        assert result11.columns.tolist() == ["id1", "variable", "val"]

        result12 = df.melt(id_vars=["id1", "id2"], value_name=value_name)
        assert result12.columns.tolist() == ["id1", "id2", "variable", "val"]

        result13 = df.melt(
            id_vars=["id1", "id2"], value_vars="A", value_name=value_name
        )
        assert result13.columns.tolist() == ["id1", "id2", "variable", "val"]

        result14 = df.melt(
            id_vars=["id1", "id2"], value_vars=["A", "B"], value_name=value_name
        )
        expected14 = DataFrame(
            {
                "id1": df["id1"].tolist() * 2,
                "id2": df["id2"].tolist() * 2,
                "variable": ["A"] * 10 + ["B"] * 10,
                value_name: (df["A"].tolist() + df["B"].tolist()),
            },
            columns=["id1", "id2", "variable", value_name],
        )
        tm.assert_frame_equal(result14, expected14)

    def test_custom_var_and_value_name(self, df, value_name, var_name):
        result15 = df.melt(var_name=var_name, value_name=value_name)
        assert result15.columns.tolist() == ["var", "val"]

        result16 = df.melt(id_vars=["id1"], var_name=var_name, value_name=value_name)
        assert result16.columns.tolist() == ["id1", "var", "val"]

        result17 = df.melt(
            id_vars=["id1", "id2"], var_name=var_name, value_name=value_name
        )
        assert result17.columns.tolist() == ["id1", "id2", "var", "val"]

        result18 = df.melt(
            id_vars=["id1", "id2"],
            value_vars="A",
            var_name=var_name,
            value_name=value_name,
        )
        assert result18.columns.tolist() == ["id1", "id2", "var", "val"]

        result19 = df.melt(
            id_vars=["id1", "id2"],
            value_vars=["A", "B"],
            var_name=var_name,
            value_name=value_name,
        )
        expected19 = DataFrame(
            {
                "id1": df["id1"].tolist() * 2,
                "id2": df["id2"].tolist() * 2,
                var_name: ["A"] * 10 + ["B"] * 10,
                value_name: (df["A"].tolist() + df["B"].tolist()),
            },
            columns=["id1", "id2", var_name, value_name],
        )
        tm.assert_frame_equal(result19, expected19)

        df20 = df.copy()
        df20.columns.name = "foo"
        result20 = df20.melt()
        assert result20.columns.tolist() == ["foo", "value"]

    @pytest.mark.parametrize("col_level", [0, "CAP"])
    def test_col_level(self, col_level, df1):
        res = df1.melt(col_level=col_level)
        assert res.columns.tolist() == ["CAP", "value"]

    def test_multiindex(self, df1):
        res = df1.melt()
        assert res.columns.tolist() == ["CAP", "low", "value"]

    @pytest.mark.parametrize(
        "col",
        [
            pd.Series(date_range("2010", periods=5, tz="US/Pacific")),
            pd.Series(["a", "b", "c", "a", "d"], dtype="category"),
            pd.Series([0, 1, 0, 0, 0]),
        ],
    )
    def test_pandas_dtypes(self, col):
        # GH 15785
        df = DataFrame(
            {"klass": range(5), "col": col, "attr1": [1, 0, 0, 0, 0], "attr2": col}
        )
        expected_value = pd.concat([pd.Series([1, 0, 0, 0, 0]), col], ignore_index=True)
        result = melt(
            df, id_vars=["klass", "col"], var_name="attribute", value_name="value"
        )
        expected = DataFrame(
            {
                0: list(range(5)) * 2,
                1: pd.concat([col] * 2, ignore_index=True),
                2: ["attr1"] * 5 + ["attr2"] * 5,
                3: expected_value,
            }
        )
        expected.columns = ["klass", "col", "attribute", "value"]
        tm.assert_frame_equal(result, expected)

    def test_preserve_category(self):
        # GH 15853
        data = DataFrame({"A": [1, 2], "B": pd.Categorical(["X", "Y"])})
        result = melt(data, ["B"], ["A"])
        expected = DataFrame(
            {"B": pd.Categorical(["X", "Y"]), "variable": ["A", "A"], "value": [1, 2]}
        )

        tm.assert_frame_equal(result, expected)

    def test_melt_missing_columns_raises(self):
        # GH-23575
        # This test is to ensure that pandas raises an error if melting is
        # attempted with column names absent from the dataframe

        # Generate data
        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, 4)), columns=list("abcd")
        )

        # Try to melt with missing `value_vars` column name
        msg = "The following id_vars or value_vars are not present in the DataFrame:"
        with pytest.raises(KeyError, match=msg):
            df.melt(["a", "b"], ["C", "d"])

        # Try to melt with missing `id_vars` column name
        with pytest.raises(KeyError, match=msg):
            df.melt(["A", "b"], ["c", "d"])

        # Multiple missing
        with pytest.raises(
            KeyError,
            match=msg,
        ):
            df.melt(["a", "b", "not_here", "or_there"], ["c", "d"])

        # Multiindex melt fails if column is missing from multilevel melt
        multi = df.copy()
        multi.columns = [list("ABCD"), list("abcd")]
        with pytest.raises(KeyError, match=msg):
            multi.melt([("E", "a")], [("B", "b")])
        # Multiindex fails if column is missing from single level melt
        with pytest.raises(KeyError, match=msg):
            multi.melt(["A"], ["F"], col_level=0)

    def test_melt_mixed_int_str_id_vars(self):
        # GH 29718
        df = DataFrame({0: ["foo"], "a": ["bar"], "b": [1], "d": [2]})
        result = melt(df, id_vars=[0, "a"], value_vars=["b", "d"])
        expected = DataFrame(
            {0: ["foo"] * 2, "a": ["bar"] * 2, "variable": list("bd"), "value": [1, 2]}
        )
        # the df's columns are mixed type and thus object -> preserves object dtype
        expected["variable"] = expected["variable"].astype(object)
        tm.assert_frame_equal(result, expected)

    def test_melt_mixed_int_str_value_vars(self):
        # GH 29718
        df = DataFrame({0: ["foo"], "a": ["bar"]})
        result = melt(df, value_vars=[0, "a"])
        expected = DataFrame({"variable": [0, "a"], "value": ["foo", "bar"]})
        tm.assert_frame_equal(result, expected)

    def test_ignore_index(self):
        # GH 17440
        df = DataFrame({"foo": [0], "bar": [1]}, index=["first"])
        result = melt(df, ignore_index=False)
        expected = DataFrame(
            {"variable": ["foo", "bar"], "value": [0, 1]}, index=["first", "first"]
        )
        tm.assert_frame_equal(result, expected)

    def test_ignore_multiindex(self):
        # GH 17440
        index = pd.MultiIndex.from_tuples(
            [("first", "second"), ("first", "third")], names=["baz", "foobar"]
        )
        df = DataFrame({"foo": [0, 1], "bar": [2, 3]}, index=index)
        result = melt(df, ignore_index=False)

        expected_index = pd.MultiIndex.from_tuples(
            [("first", "second"), ("first", "third")] * 2, names=["baz", "foobar"]
        )
        expected = DataFrame(
            {"variable": ["foo"] * 2 + ["bar"] * 2, "value": [0, 1, 2, 3]},
            index=expected_index,
        )

        tm.assert_frame_equal(result, expected)

    def test_ignore_index_name_and_type(self):
        # GH 17440
        index = Index(["foo", "bar"], dtype="category", name="baz")
        df = DataFrame({"x": [0, 1], "y": [2, 3]}, index=index)
        result = melt(df, ignore_index=False)

        expected_index = Index(["foo", "bar"] * 2, dtype="category", name="baz")
        expected = DataFrame(
            {"variable": ["x", "x", "y", "y"], "value": [0, 1, 2, 3]},
            index=expected_index,
        )

        tm.assert_frame_equal(result, expected)

    def test_melt_with_duplicate_columns(self):
        # GH#41951
        df = DataFrame([["id", 2, 3]], columns=["a", "b", "b"])
        result = df.melt(id_vars=["a"], value_vars=["b"])
        expected = DataFrame(
            [["id", "b", 2], ["id", "b", 3]], columns=["a", "variable", "value"]
        )
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("dtype", ["Int8", "Int64"])
    def test_melt_ea_dtype(self, dtype):
        # GH#41570
        df = DataFrame(
            {
                "a": pd.Series([1, 2], dtype="Int8"),
                "b": pd.Series([3, 4], dtype=dtype),
            }
        )
        result = df.melt()
        expected = DataFrame(
            {
                "variable": ["a", "a", "b", "b"],
                "value": pd.Series([1, 2, 3, 4], dtype=dtype),
            }
        )
        tm.assert_frame_equal(result, expected)

    def test_melt_ea_columns(self):
        # GH 54297
        df = DataFrame(
            {
                "A": {0: "a", 1: "b", 2: "c"},
                "B": {0: 1, 1: 3, 2: 5},
                "C": {0: 2, 1: 4, 2: 6},
            }
        )
        df.columns = df.columns.astype("string[python]")
        result = df.melt(id_vars=["A"], value_vars=["B"])
        expected = DataFrame(
            {
                "A": list("abc"),
                "variable": pd.Series(["B"] * 3, dtype="string[python]"),
                "value": [1, 3, 5],
            }
        )
        tm.assert_frame_equal(result, expected)

    def test_melt_preserves_datetime(self):
        df = DataFrame(
            data=[
                {
                    "type": "A0",
                    "start_date": pd.Timestamp("2023/03/01", tz="Asia/Tokyo"),
                    "end_date": pd.Timestamp("2023/03/10", tz="Asia/Tokyo"),
                },
                {
                    "type": "A1",
                    "start_date": pd.Timestamp("2023/03/01", tz="Asia/Tokyo"),
                    "end_date": pd.Timestamp("2023/03/11", tz="Asia/Tokyo"),
                },
            ],
            index=["aaaa", "bbbb"],
        )
        result = df.melt(
            id_vars=["type"],
            value_vars=["start_date", "end_date"],
            var_name="start/end",
            value_name="date",
        )
        expected = DataFrame(
            {
                "type": {0: "A0", 1: "A1", 2: "A0", 3: "A1"},
                "start/end": {
                    0: "start_date",
                    1: "start_date",
                    2: "end_date",
                    3: "end_date",
                },
                "date": {
                    0: pd.Timestamp("2023-03-01 00:00:00+0900", tz="Asia/Tokyo"),
                    1: pd.Timestamp("2023-03-01 00:00:00+0900", tz="Asia/Tokyo"),
                    2: pd.Timestamp("2023-03-10 00:00:00+0900", tz="Asia/Tokyo"),
                    3: pd.Timestamp("2023-03-11 00:00:00+0900", tz="Asia/Tokyo"),
                },
            }
        )
        tm.assert_frame_equal(result, expected)

    def test_melt_allows_non_scalar_id_vars(self):
        df = DataFrame(
            data={"a": [1, 2, 3], "b": [4, 5, 6]},
            index=["11", "22", "33"],
        )
        result = df.melt(
            id_vars="a",
            var_name=0,
            value_name=1,
        )
        expected = DataFrame({"a": [1, 2, 3], 0: ["b"] * 3, 1: [4, 5, 6]})
        tm.assert_frame_equal(result, expected)

    def test_melt_allows_non_string_var_name(self):
        df = DataFrame(
            data={"a": [1, 2, 3], "b": [4, 5, 6]},
            index=["11", "22", "33"],
        )
        result = df.melt(
            id_vars=["a"],
            var_name=0,
            value_name=1,
        )
        expected = DataFrame({"a": [1, 2, 3], 0: ["b"] * 3, 1: [4, 5, 6]})
        tm.assert_frame_equal(result, expected)

    def test_melt_non_scalar_var_name_raises(self):
        df = DataFrame(
            data={"a": [1, 2, 3], "b": [4, 5, 6]},
            index=["11", "22", "33"],
        )
        with pytest.raises(ValueError, match=r".* must be a scalar."):
            df.melt(id_vars=["a"], var_name=[1, 2])


class TestLreshape:
    def test_pairs(self):
        data = {
            "birthdt": [
                "08jan2009",
                "20dec2008",
                "30dec2008",
                "21dec2008",
                "11jan2009",
            ],
            "birthwt": [1766, 3301, 1454, 3139, 4133],
            "id": [101, 102, 103, 104, 105],
            "sex": ["Male", "Female", "Female", "Female", "Female"],
            "visitdt1": [
                "11jan2009",
                "22dec2008",
                "04jan2009",
                "29dec2008",
                "20jan2009",
            ],
            "visitdt2": ["21jan2009", np.nan, "22jan2009", "31dec2008", "03feb2009"],
            "visitdt3": ["05feb2009", np.nan, np.nan, "02jan2009", "15feb2009"],
            "wt1": [1823, 3338, 1549, 3298, 4306],
            "wt2": [2011.0, np.nan, 1892.0, 3338.0, 4575.0],
            "wt3": [2293.0, np.nan, np.nan, 3377.0, 4805.0],
        }

        df = DataFrame(data)

        spec = {
            "visitdt": [f"visitdt{i:d}" for i in range(1, 4)],
            "wt": [f"wt{i:d}" for i in range(1, 4)],
        }
        result = lreshape(df, spec)

        exp_data = {
            "birthdt": [
                "08jan2009",
                "20dec2008",
                "30dec2008",
                "21dec2008",
                "11jan2009",
                "08jan2009",
                "30dec2008",
                "21dec2008",
                "11jan2009",
                "08jan2009",
                "21dec2008",
                "11jan2009",
            ],
            "birthwt": [
                1766,
                3301,
                1454,
                3139,
                4133,
                1766,
                1454,
                3139,
                4133,
                1766,
                3139,
                4133,
            ],
            "id": [101, 102, 103, 104, 105, 101, 103, 104, 105, 101, 104, 105],
            "sex": [
                "Male",
                "Female",
                "Female",
                "Female",
                "Female",
                "Male",
                "Female",
                "Female",
                "Female",
                "Male",
                "Female",
                "Female",
            ],
            "visitdt": [
                "11jan2009",
                "22dec2008",
                "04jan2009",
                "29dec2008",
                "20jan2009",
                "21jan2009",
                "22jan2009",
                "31dec2008",
                "03feb2009",
                "05feb2009",
                "02jan2009",
                "15feb2009",
            ],
            "wt": [
                1823.0,
                3338.0,
                1549.0,
                3298.0,
                4306.0,
                2011.0,
                1892.0,
                3338.0,
                4575.0,
                2293.0,
                3377.0,
                4805.0,
            ],
        }
        exp = DataFrame(exp_data, columns=result.columns)
        tm.assert_frame_equal(result, exp)

        result = lreshape(df, spec, dropna=False)
        exp_data = {
            "birthdt": [
                "08jan2009",
                "20dec2008",
                "30dec2008",
                "21dec2008",
                "11jan2009",
                "08jan2009",
                "20dec2008",
                "30dec2008",
                "21dec2008",
                "11jan2009",
                "08jan2009",
                "20dec2008",
                "30dec2008",
                "21dec2008",
                "11jan2009",
            ],
            "birthwt": [
                1766,
                3301,
                1454,
                3139,
                4133,
                1766,
                3301,
                1454,
                3139,
                4133,
                1766,
                3301,
                1454,
                3139,
                4133,
            ],
            "id": [
                101,
                102,
                103,
                104,
                105,
                101,
                102,
                103,
                104,
                105,
                101,
                102,
                103,
                104,
                105,
            ],
            "sex": [
                "Male",
                "Female",
                "Female",
                "Female",
                "Female",
                "Male",
                "Female",
                "Female",
                "Female",
                "Female",
                "Male",
                "Female",
                "Female",
                "Female",
                "Female",
            ],
            "visitdt": [
                "11jan2009",
                "22dec2008",
                "04jan2009",
                "29dec2008",
                "20jan2009",
                "21jan2009",
                np.nan,
                "22jan2009",
                "31dec2008",
                "03feb2009",
                "05feb2009",
                np.nan,
                np.nan,
                "02jan2009",
                "15feb2009",
            ],
            "wt": [
                1823.0,
                3338.0,
                1549.0,
                3298.0,
                4306.0,
                2011.0,
                np.nan,
                1892.0,
                3338.0,
                4575.0,
                2293.0,
                np.nan,
                np.nan,
                3377.0,
                4805.0,
            ],
        }
        exp = DataFrame(exp_data, columns=result.columns)
        tm.assert_frame_equal(result, exp)

        spec = {
            "visitdt": [f"visitdt{i:d}" for i in range(1, 3)],
            "wt": [f"wt{i:d}" for i in range(1, 4)],
        }
        msg = "All column lists must be same length"
        with pytest.raises(ValueError, match=msg):
            lreshape(df, spec)


class TestWideToLong:
    def test_simple(self):
        x = np.random.default_rng(2).standard_normal(3)
        df = DataFrame(
            {
                "A1970": {0: "a", 1: "b", 2: "c"},
                "A1980": {0: "d", 1: "e", 2: "f"},
                "B1970": {0: 2.5, 1: 1.2, 2: 0.7},
                "B1980": {0: 3.2, 1: 1.3, 2: 0.1},
                "X": dict(zip(range(3), x)),
            }
        )
        df["id"] = df.index
        exp_data = {
            "X": x.tolist() + x.tolist(),
            "A": ["a", "b", "c", "d", "e", "f"],
            "B": [2.5, 1.2, 0.7, 3.2, 1.3, 0.1],
            "year": [1970, 1970, 1970, 1980, 1980, 1980],
            "id": [0, 1, 2, 0, 1, 2],
        }
        expected = DataFrame(exp_data)
        expected = expected.set_index(["id", "year"])[["X", "A", "B"]]
        result = wide_to_long(df, ["A", "B"], i="id", j="year")
        tm.assert_frame_equal(result, expected)

    def test_stubs(self):
        # GH9204 wide_to_long call should not modify 'stubs' list
        df = DataFrame([[0, 1, 2, 3, 8], [4, 5, 6, 7, 9]])
        df.columns = ["id", "inc1", "inc2", "edu1", "edu2"]
        stubs = ["inc", "edu"]

        wide_to_long(df, stubs, i="id", j="age")

        assert stubs == ["inc", "edu"]

    def test_separating_character(self):
        # GH14779

        x = np.random.default_rng(2).standard_normal(3)
        df = DataFrame(
            {
                "A.1970": {0: "a", 1: "b", 2: "c"},
                "A.1980": {0: "d", 1: "e", 2: "f"},
                "B.1970": {0: 2.5, 1: 1.2, 2: 0.7},
                "B.1980": {0: 3.2, 1: 1.3, 2: 0.1},
                "X": dict(zip(range(3), x)),
            }
        )
        df["id"] = df.index
        exp_data = {
            "X": x.tolist() + x.tolist(),
            "A": ["a", "b", "c", "d", "e", "f"],
            "B": [2.5, 1.2, 0.7, 3.2, 1.3, 0.1],
            "year": [1970, 1970, 1970, 1980, 1980, 1980],
            "id": [0, 1, 2, 0, 1, 2],
        }
        expected = DataFrame(exp_data)
        expected = expected.set_index(["id", "year"])[["X", "A", "B"]]
        result = wide_to_long(df, ["A", "B"], i="id", j="year", sep=".")
        tm.assert_frame_equal(result, expected)

    def test_escapable_characters(self):
        x = np.random.default_rng(2).standard_normal(3)
        df = DataFrame(
            {
                "A(quarterly)1970": {0: "a", 1: "b", 2: "c"},
                "A(quarterly)1980": {0: "d", 1: "e", 2: "f"},
                "B(quarterly)1970": {0: 2.5, 1: 1.2, 2: 0.7},
                "B(quarterly)1980": {0: 3.2, 1: 1.3, 2: 0.1},
                "X": dict(zip(range(3), x)),
            }
        )
        df["id"] = df.index
        exp_data = {
            "X": x.tolist() + x.tolist(),
            "A(quarterly)": ["a", "b", "c", "d", "e", "f"],
            "B(quarterly)": [2.5, 1.2, 0.7, 3.2, 1.3, 0.1],
            "year": [1970, 1970, 1970, 1980, 1980, 1980],
            "id": [0, 1, 2, 0, 1, 2],
        }
        expected = DataFrame(exp_data)
        expected = expected.set_index(["id", "year"])[
            ["X", "A(quarterly)", "B(quarterly)"]
        ]
        result = wide_to_long(df, ["A(quarterly)", "B(quarterly)"], i="id", j="year")
        tm.assert_frame_equal(result, expected)

    def test_unbalanced(self):
        # test that we can have a varying amount of time variables
        df = DataFrame(
            {
                "A2010": [1.0, 2.0],
                "A2011": [3.0, 4.0],
                "B2010": [5.0, 6.0],
                "X": ["X1", "X2"],
            }
        )
        df["id"] = df.index
        exp_data = {
            "X": ["X1", "X2", "X1", "X2"],
            "A": [1.0, 2.0, 3.0, 4.0],
            "B": [5.0, 6.0, np.nan, np.nan],
            "id": [0, 1, 0, 1],
            "year": [2010, 2010, 2011, 2011],
        }
        expected = DataFrame(exp_data)
        expected = expected.set_index(["id", "year"])[["X", "A", "B"]]
        result = wide_to_long(df, ["A", "B"], i="id", j="year")
        tm.assert_frame_equal(result, expected)

    def test_character_overlap(self):
        # Test we handle overlapping characters in both id_vars and value_vars
        df = DataFrame(
            {
                "A11": ["a11", "a22", "a33"],
                "A12": ["a21", "a22", "a23"],
                "B11": ["b11", "b12", "b13"],
                "B12": ["b21", "b22", "b23"],
                "BB11": [1, 2, 3],
                "BB12": [4, 5, 6],
                "BBBX": [91, 92, 93],
                "BBBZ": [91, 92, 93],
            }
        )
        df["id"] = df.index
        expected = DataFrame(
            {
                "BBBX": [91, 92, 93, 91, 92, 93],
                "BBBZ": [91, 92, 93, 91, 92, 93],
                "A": ["a11", "a22", "a33", "a21", "a22", "a23"],
                "B": ["b11", "b12", "b13", "b21", "b22", "b23"],
                "BB": [1, 2, 3, 4, 5, 6],
                "id": [0, 1, 2, 0, 1, 2],
                "year": [11, 11, 11, 12, 12, 12],
            }
        )
        expected = expected.set_index(["id", "year"])[["BBBX", "BBBZ", "A", "B", "BB"]]
        result = wide_to_long(df, ["A", "B", "BB"], i="id", j="year")
        tm.assert_frame_equal(result.sort_index(axis=1), expected.sort_index(axis=1))

    def test_invalid_separator(self):
        # if an invalid separator is supplied a empty data frame is returned
        sep = "nope!"
        df = DataFrame(
            {
                "A2010": [1.0, 2.0],
                "A2011": [3.0, 4.0],
                "B2010": [5.0, 6.0],
                "X": ["X1", "X2"],
            }
        )
        df["id"] = df.index
        exp_data = {
            "X": "",
            "A2010": [],
            "A2011": [],
            "B2010": [],
            "id": [],
            "year": [],
            "A": [],
            "B": [],
        }
        expected = DataFrame(exp_data).astype({"year": np.int64})
        expected = expected.set_index(["id", "year"])[
            ["X", "A2010", "A2011", "B2010", "A", "B"]
        ]
        expected.index = expected.index.set_levels([0, 1], level=0)
        result = wide_to_long(df, ["A", "B"], i="id", j="year", sep=sep)
        tm.assert_frame_equal(result.sort_index(axis=1), expected.sort_index(axis=1))

    def test_num_string_disambiguation(self):
        # Test that we can disambiguate number value_vars from
        # string value_vars
        df = DataFrame(
            {
                "A11": ["a11", "a22", "a33"],
                "A12": ["a21", "a22", "a23"],
                "B11": ["b11", "b12", "b13"],
                "B12": ["b21", "b22", "b23"],
                "BB11": [1, 2, 3],
                "BB12": [4, 5, 6],
                "Arating": [91, 92, 93],
                "Arating_old": [91, 92, 93],
            }
        )
        df["id"] = df.index
        expected = DataFrame(
            {
                "Arating": [91, 92, 93, 91, 92, 93],
                "Arating_old": [91, 92, 93, 91, 92, 93],
                "A": ["a11", "a22", "a33", "a21", "a22", "a23"],
                "B": ["b11", "b12", "b13", "b21", "b22", "b23"],
                "BB": [1, 2, 3, 4, 5, 6],
                "id": [0, 1, 2, 0, 1, 2],
                "year": [11, 11, 11, 12, 12, 12],
            }
        )
        expected = expected.set_index(["id", "year"])[
            ["Arating", "Arating_old", "A", "B", "BB"]
        ]
        result = wide_to_long(df, ["A", "B", "BB"], i="id", j="year")
        tm.assert_frame_equal(result.sort_index(axis=1), expected.sort_index(axis=1))

    def test_invalid_suffixtype(self):
        # If all stubs names end with a string, but a numeric suffix is
        # assumed,  an empty data frame is returned
        df = DataFrame(
            {
                "Aone": [1.0, 2.0],
                "Atwo": [3.0, 4.0],
                "Bone": [5.0, 6.0],
                "X": ["X1", "X2"],
            }
        )
        df["id"] = df.index
        exp_data = {
            "X": "",
            "Aone": [],
            "Atwo": [],
            "Bone": [],
            "id": [],
            "year": [],
            "A": [],
            "B": [],
        }
        expected = DataFrame(exp_data).astype({"year": np.int64})

        expected = expected.set_index(["id", "year"])
        expected.index = expected.index.set_levels([0, 1], level=0)
        result = wide_to_long(df, ["A", "B"], i="id", j="year")
        tm.assert_frame_equal(result.sort_index(axis=1), expected.sort_index(axis=1))

    def test_multiple_id_columns(self):
        # Taken from http://www.ats.ucla.edu/stat/stata/modules/reshapel.htm
        df = DataFrame(
            {
                "famid": [1, 1, 1, 2, 2, 2, 3, 3, 3],
                "birth": [1, 2, 3, 1, 2, 3, 1, 2, 3],
                "ht1": [2.8, 2.9, 2.2, 2, 1.8, 1.9, 2.2, 2.3, 2.1],
                "ht2": [3.4, 3.8, 2.9, 3.2, 2.8, 2.4, 3.3, 3.4, 2.9],
            }
        )
        expected = DataFrame(
            {
                "ht": [
                    2.8,
                    3.4,
                    2.9,
                    3.8,
                    2.2,
                    2.9,
                    2.0,
                    3.2,
                    1.8,
                    2.8,
                    1.9,
                    2.4,
                    2.2,
                    3.3,
                    2.3,
                    3.4,
                    2.1,
                    2.9,
                ],
                "famid": [1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3],
                "birth": [1, 1, 2, 2, 3, 3, 1, 1, 2, 2, 3, 3, 1, 1, 2, 2, 3, 3],
                "age": [1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2],
            }
        )
        expected = expected.set_index(["famid", "birth", "age"])[["ht"]]
        result = wide_to_long(df, "ht", i=["famid", "birth"], j="age")
        tm.assert_frame_equal(result, expected)

    def test_non_unique_idvars(self):
        # GH16382
        # Raise an error message if non unique id vars (i) are passed
        df = DataFrame(
            {"A_A1": [1, 2, 3, 4, 5], "B_B1": [1, 2, 3, 4, 5], "x": [1, 1, 1, 1, 1]}
        )
        msg = "the id variables need to uniquely identify each row"
        with pytest.raises(ValueError, match=msg):
            wide_to_long(df, ["A_A", "B_B"], i="x", j="colname")

    def test_cast_j_int(self):
        df = DataFrame(
            {
                "actor_1": ["CCH Pounder", "Johnny Depp", "Christoph Waltz"],
                "actor_2": ["Joel David Moore", "Orlando Bloom", "Rory Kinnear"],
                "actor_fb_likes_1": [1000.0, 40000.0, 11000.0],
                "actor_fb_likes_2": [936.0, 5000.0, 393.0],
                "title": ["Avatar", "Pirates of the Caribbean", "Spectre"],
            }
        )

        expected = DataFrame(
            {
                "actor": [
                    "CCH Pounder",
                    "Johnny Depp",
                    "Christoph Waltz",
                    "Joel David Moore",
                    "Orlando Bloom",
                    "Rory Kinnear",
                ],
                "actor_fb_likes": [1000.0, 40000.0, 11000.0, 936.0, 5000.0, 393.0],
                "num": [1, 1, 1, 2, 2, 2],
                "title": [
                    "Avatar",
                    "Pirates of the Caribbean",
                    "Spectre",
                    "Avatar",
                    "Pirates of the Caribbean",
                    "Spectre",
                ],
            }
        ).set_index(["title", "num"])
        result = wide_to_long(
            df, ["actor", "actor_fb_likes"], i="title", j="num", sep="_"
        )

        tm.assert_frame_equal(result, expected)

    def test_identical_stubnames(self):
        df = DataFrame(
            {
                "A2010": [1.0, 2.0],
                "A2011": [3.0, 4.0],
                "B2010": [5.0, 6.0],
                "A": ["X1", "X2"],
            }
        )
        msg = "stubname can't be identical to a column name"
        with pytest.raises(ValueError, match=msg):
            wide_to_long(df, ["A", "B"], i="A", j="colname")

    def test_nonnumeric_suffix(self):
        df = DataFrame(
            {
                "treatment_placebo": [1.0, 2.0],
                "treatment_test": [3.0, 4.0],
                "result_placebo": [5.0, 6.0],
                "A": ["X1", "X2"],
            }
        )
        expected = DataFrame(
            {
                "A": ["X1", "X2", "X1", "X2"],
                "colname": ["placebo", "placebo", "test", "test"],
                "result": [5.0, 6.0, np.nan, np.nan],
                "treatment": [1.0, 2.0, 3.0, 4.0],
            }
        )
        expected = expected.set_index(["A", "colname"])
        result = wide_to_long(
            df, ["result", "treatment"], i="A", j="colname", suffix="[a-z]+", sep="_"
        )
        tm.assert_frame_equal(result, expected)

    def test_mixed_type_suffix(self):
        df = DataFrame(
            {
                "A": ["X1", "X2"],
                "result_1": [0, 9],
                "result_foo": [5.0, 6.0],
                "treatment_1": [1.0, 2.0],
                "treatment_foo": [3.0, 4.0],
            }
        )
        expected = DataFrame(
            {
                "A": ["X1", "X2", "X1", "X2"],
                "colname": ["1", "1", "foo", "foo"],
                "result": [0.0, 9.0, 5.0, 6.0],
                "treatment": [1.0, 2.0, 3.0, 4.0],
            }
        ).set_index(["A", "colname"])
        result = wide_to_long(
            df, ["result", "treatment"], i="A", j="colname", suffix=".+", sep="_"
        )
        tm.assert_frame_equal(result, expected)

    def test_float_suffix(self):
        df = DataFrame(
            {
                "treatment_1.1": [1.0, 2.0],
                "treatment_2.1": [3.0, 4.0],
                "result_1.2": [5.0, 6.0],
                "result_1": [0, 9],
                "A": ["X1", "X2"],
            }
        )
        expected = DataFrame(
            {
                "A": ["X1", "X2", "X1", "X2", "X1", "X2", "X1", "X2"],
                "colname": [1.2, 1.2, 1.0, 1.0, 1.1, 1.1, 2.1, 2.1],
                "result": [5.0, 6.0, 0.0, 9.0, np.nan, np.nan, np.nan, np.nan],
                "treatment": [np.nan, np.nan, np.nan, np.nan, 1.0, 2.0, 3.0, 4.0],
            }
        )
        expected = expected.set_index(["A", "colname"])
        result = wide_to_long(
            df, ["result", "treatment"], i="A", j="colname", suffix="[0-9.]+", sep="_"
        )
        tm.assert_frame_equal(result, expected)

    def test_col_substring_of_stubname(self):
        # GH22468
        # Don't raise ValueError when a column name is a substring
        # of a stubname that's been passed as a string
        wide_data = {
            "node_id": {0: 0, 1: 1, 2: 2, 3: 3, 4: 4},
            "A": {0: 0.80, 1: 0.0, 2: 0.25, 3: 1.0, 4: 0.81},
            "PA0": {0: 0.74, 1: 0.56, 2: 0.56, 3: 0.98, 4: 0.6},
            "PA1": {0: 0.77, 1: 0.64, 2: 0.52, 3: 0.98, 4: 0.67},
            "PA3": {0: 0.34, 1: 0.70, 2: 0.52, 3: 0.98, 4: 0.67},
        }
        wide_df = DataFrame.from_dict(wide_data)
        expected = wide_to_long(wide_df, stubnames=["PA"], i=["node_id", "A"], j="time")
        result = wide_to_long(wide_df, stubnames="PA", i=["node_id", "A"], j="time")
        tm.assert_frame_equal(result, expected)

    def test_raise_of_column_name_value(self):
        # GH34731, enforced in 2.0
        # raise a ValueError if the resultant value column name matches
        # a name in the dataframe already (default name is "value")
        df = DataFrame({"col": list("ABC"), "value": range(10, 16, 2)})

        with pytest.raises(
            ValueError, match=re.escape("value_name (value) cannot match")
        ):
            df.melt(id_vars="value", value_name="value")

    def test_missing_stubname(self, request, any_string_dtype, using_infer_string):
        if using_infer_string and any_string_dtype == "object":
            # triggers object dtype inference warning of dtype=object
            request.applymarker(pytest.mark.xfail(reason="TODO(infer_string)"))
        # GH46044
        df = DataFrame({"id": ["1", "2"], "a-1": [100, 200], "a-2": [300, 400]})
        df = df.astype({"id": any_string_dtype})
        result = wide_to_long(
            df,
            stubnames=["a", "b"],
            i="id",
            j="num",
            sep="-",
        )
        index = Index(
            [("1", 1), ("2", 1), ("1", 2), ("2", 2)],
            name=("id", "num"),
        )
        expected = DataFrame(
            {"a": [100, 200, 300, 400], "b": [np.nan] * 4},
            index=index,
        )
        new_level = expected.index.levels[0].astype(any_string_dtype)
        if any_string_dtype == "object":
            new_level = expected.index.levels[0].astype("str")
        expected.index = expected.index.set_levels(new_level, level=0)
        tm.assert_frame_equal(result, expected)


def test_wide_to_long_string_columns(string_storage):
    # GH 57066
    string_dtype = pd.StringDtype(string_storage, na_value=np.nan)
    df = DataFrame(
        {
            "ID": {0: 1},
            "R_test1": {0: 1},
            "R_test2": {0: 1},
            "R_test3": {0: 2},
            "D": {0: 1},
        }
    )
    df.columns = df.columns.astype(string_dtype)
    result = wide_to_long(
        df, stubnames="R", i="ID", j="UNPIVOTED", sep="_", suffix=".*"
    )
    expected = DataFrame(
        [[1, 1], [1, 1], [1, 2]],
        columns=Index(["D", "R"]),
        index=pd.MultiIndex.from_arrays(
            [
                [1, 1, 1],
                Index(["test1", "test2", "test3"], dtype=string_dtype),
            ],
            names=["ID", "UNPIVOTED"],
        ),
    )
    tm.assert_frame_equal(result, expected)
