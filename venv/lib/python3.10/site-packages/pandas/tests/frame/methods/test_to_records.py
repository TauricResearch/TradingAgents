from collections import abc
import email
from email.parser import Parser

import numpy as np
import pytest

from pandas import (
    CategoricalDtype,
    DataFrame,
    MultiIndex,
    Series,
    Timestamp,
    date_range,
)
import pandas._testing as tm


class TestDataFrameToRecords:
    def test_to_records_timeseries(self):
        index = date_range("1/1/2000", periods=10)
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 3)),
            index=index,
            columns=["a", "b", "c"],
        )

        result = df.to_records()
        assert result["index"].dtype == "M8[ns]"

        result = df.to_records(index=False)

    def test_to_records_dt64(self):
        df = DataFrame(
            [["one", "two", "three"], ["four", "five", "six"]],
            index=date_range("2012-01-01", "2012-01-02"),
        )

        expected = df.index.values[0]
        result = df.to_records()["index"][0]
        assert expected == result

    def test_to_records_dt64tz_column(self):
        # GH#32535 dont less tz in to_records
        df = DataFrame({"A": date_range("2012-01-01", "2012-01-02", tz="US/Eastern")})

        result = df.to_records()

        assert result.dtype["A"] == object
        val = result[0][1]
        assert isinstance(val, Timestamp)
        assert val == df.loc[0, "A"]

    def test_to_records_with_multindex(self):
        # GH#3189
        index = [
            ["bar", "bar", "baz", "baz", "foo", "foo", "qux", "qux"],
            ["one", "two", "one", "two", "one", "two", "one", "two"],
        ]
        data = np.zeros((8, 4))
        df = DataFrame(data, index=index)
        r = df.to_records(index=True)["level_0"]
        assert "bar" in r
        assert "one" not in r

    def test_to_records_with_Mapping_type(self):
        abc.Mapping.register(email.message.Message)

        headers = Parser().parsestr(
            "From: <user@example.com>\n"
            "To: <someone_else@example.com>\n"
            "Subject: Test message\n"
            "\n"
            "Body would go here\n"
        )

        frame = DataFrame.from_records([headers])
        all(x in frame for x in ["Type", "Subject", "From"])

    def test_to_records_floats(self):
        df = DataFrame(np.random.default_rng(2).random((10, 10)))
        df.to_records()

    def test_to_records_index_name(self):
        df = DataFrame(np.random.default_rng(2).standard_normal((3, 3)))
        df.index.name = "X"
        rs = df.to_records()
        assert "X" in rs.dtype.fields

        df = DataFrame(np.random.default_rng(2).standard_normal((3, 3)))
        rs = df.to_records()
        assert "index" in rs.dtype.fields

        df.index = MultiIndex.from_tuples([("a", "x"), ("a", "y"), ("b", "z")])
        df.index.names = ["A", None]
        result = df.to_records()
        expected = np.rec.fromarrays(
            [np.array(["a", "a", "b"]), np.array(["x", "y", "z"])]
            + [np.asarray(df.iloc[:, i]) for i in range(3)],
            dtype={
                "names": ["A", "level_1", "0", "1", "2"],
                "formats": [
                    "O",
                    "O",
                    f"{tm.ENDIAN}f8",
                    f"{tm.ENDIAN}f8",
                    f"{tm.ENDIAN}f8",
                ],
            },
        )
        tm.assert_numpy_array_equal(result, expected)

    def test_to_records_with_unicode_index(self):
        # GH#13172
        # unicode_literals conflict with to_records
        result = DataFrame([{"a": "x", "b": "y"}]).set_index("a").to_records()
        expected = np.rec.array([("x", "y")], dtype=[("a", "O"), ("b", "O")])
        tm.assert_almost_equal(result, expected)

    def test_to_records_index_dtype(self):
        # GH 47263: consistent data types for Index and MultiIndex
        df = DataFrame(
            {
                1: date_range("2022-01-01", periods=2),
                2: date_range("2022-01-01", periods=2),
                3: date_range("2022-01-01", periods=2),
            }
        )

        expected = np.rec.array(
            [
                ("2022-01-01", "2022-01-01", "2022-01-01"),
                ("2022-01-02", "2022-01-02", "2022-01-02"),
            ],
            dtype=[
                ("1", f"{tm.ENDIAN}M8[ns]"),
                ("2", f"{tm.ENDIAN}M8[ns]"),
                ("3", f"{tm.ENDIAN}M8[ns]"),
            ],
        )

        result = df.to_records(index=False)
        tm.assert_almost_equal(result, expected)

        result = df.set_index(1).to_records(index=True)
        tm.assert_almost_equal(result, expected)

        result = df.set_index([1, 2]).to_records(index=True)
        tm.assert_almost_equal(result, expected)

    def test_to_records_with_unicode_column_names(self):
        # xref issue: https://github.com/numpy/numpy/issues/2407
        # Issue GH#11879. to_records used to raise an exception when used
        # with column names containing non-ascii characters in Python 2
        result = DataFrame(data={"accented_name_é": [1.0]}).to_records()

        # Note that numpy allows for unicode field names but dtypes need
        # to be specified using dictionary instead of list of tuples.
        expected = np.rec.array(
            [(0, 1.0)],
            dtype={"names": ["index", "accented_name_é"], "formats": ["=i8", "=f8"]},
        )
        tm.assert_almost_equal(result, expected)

    def test_to_records_with_categorical(self):
        # GH#8626

        # dict creation
        df = DataFrame({"A": list("abc")}, dtype="category")
        expected = Series(list("abc"), dtype="category", name="A")
        tm.assert_series_equal(df["A"], expected)

        # list-like creation
        df = DataFrame(list("abc"), dtype="category")
        expected = Series(list("abc"), dtype="category", name=0)
        tm.assert_series_equal(df[0], expected)

        # to record array
        # this coerces
        result = df.to_records()
        expected = np.rec.array(
            [(0, "a"), (1, "b"), (2, "c")], dtype=[("index", "=i8"), ("0", "O")]
        )
        tm.assert_almost_equal(result, expected)

    @pytest.mark.parametrize(
        "kwargs,expected",
        [
            # No dtypes --> default to array dtypes.
            (
                {},
                np.rec.array(
                    [(0, 1, 0.2, "a"), (1, 2, 1.5, "bc")],
                    dtype=[
                        ("index", f"{tm.ENDIAN}i8"),
                        ("A", f"{tm.ENDIAN}i8"),
                        ("B", f"{tm.ENDIAN}f8"),
                        ("C", "O"),
                    ],
                ),
            ),
            # Should have no effect in this case.
            (
                {"index": True},
                np.rec.array(
                    [(0, 1, 0.2, "a"), (1, 2, 1.5, "bc")],
                    dtype=[
                        ("index", f"{tm.ENDIAN}i8"),
                        ("A", f"{tm.ENDIAN}i8"),
                        ("B", f"{tm.ENDIAN}f8"),
                        ("C", "O"),
                    ],
                ),
            ),
            # Column dtype applied across the board. Index unaffected.
            (
                {"column_dtypes": f"{tm.ENDIAN}U4"},
                np.rec.array(
                    [("0", "1", "0.2", "a"), ("1", "2", "1.5", "bc")],
                    dtype=[
                        ("index", f"{tm.ENDIAN}i8"),
                        ("A", f"{tm.ENDIAN}U4"),
                        ("B", f"{tm.ENDIAN}U4"),
                        ("C", f"{tm.ENDIAN}U4"),
                    ],
                ),
            ),
            # Index dtype applied across the board. Columns unaffected.
            (
                {"index_dtypes": f"{tm.ENDIAN}U1"},
                np.rec.array(
                    [("0", 1, 0.2, "a"), ("1", 2, 1.5, "bc")],
                    dtype=[
                        ("index", f"{tm.ENDIAN}U1"),
                        ("A", f"{tm.ENDIAN}i8"),
                        ("B", f"{tm.ENDIAN}f8"),
                        ("C", "O"),
                    ],
                ),
            ),
            # Pass in a type instance.
            (
                {"column_dtypes": str},
                np.rec.array(
                    [("0", "1", "0.2", "a"), ("1", "2", "1.5", "bc")],
                    dtype=[
                        ("index", f"{tm.ENDIAN}i8"),
                        ("A", f"{tm.ENDIAN}U"),
                        ("B", f"{tm.ENDIAN}U"),
                        ("C", f"{tm.ENDIAN}U"),
                    ],
                ),
            ),
            # Pass in a dtype instance.
            (
                {"column_dtypes": np.dtype(np.str_)},
                np.rec.array(
                    [("0", "1", "0.2", "a"), ("1", "2", "1.5", "bc")],
                    dtype=[
                        ("index", f"{tm.ENDIAN}i8"),
                        ("A", f"{tm.ENDIAN}U"),
                        ("B", f"{tm.ENDIAN}U"),
                        ("C", f"{tm.ENDIAN}U"),
                    ],
                ),
            ),
            # Pass in a dictionary (name-only).
            (
                {
                    "column_dtypes": {
                        "A": np.int8,
                        "B": np.float32,
                        "C": f"{tm.ENDIAN}U2",
                    }
                },
                np.rec.array(
                    [("0", "1", "0.2", "a"), ("1", "2", "1.5", "bc")],
                    dtype=[
                        ("index", f"{tm.ENDIAN}i8"),
                        ("A", "i1"),
                        ("B", f"{tm.ENDIAN}f4"),
                        ("C", f"{tm.ENDIAN}U2"),
                    ],
                ),
            ),
            # Pass in a dictionary (indices-only).
            (
                {"index_dtypes": {0: "int16"}},
                np.rec.array(
                    [(0, 1, 0.2, "a"), (1, 2, 1.5, "bc")],
                    dtype=[
                        ("index", "i2"),
                        ("A", f"{tm.ENDIAN}i8"),
                        ("B", f"{tm.ENDIAN}f8"),
                        ("C", "O"),
                    ],
                ),
            ),
            # Ignore index mappings if index is not True.
            (
                {"index": False, "index_dtypes": f"{tm.ENDIAN}U2"},
                np.rec.array(
                    [(1, 0.2, "a"), (2, 1.5, "bc")],
                    dtype=[
                        ("A", f"{tm.ENDIAN}i8"),
                        ("B", f"{tm.ENDIAN}f8"),
                        ("C", "O"),
                    ],
                ),
            ),
            # Non-existent names / indices in mapping should not error.
            (
                {"index_dtypes": {0: "int16", "not-there": "float32"}},
                np.rec.array(
                    [(0, 1, 0.2, "a"), (1, 2, 1.5, "bc")],
                    dtype=[
                        ("index", "i2"),
                        ("A", f"{tm.ENDIAN}i8"),
                        ("B", f"{tm.ENDIAN}f8"),
                        ("C", "O"),
                    ],
                ),
            ),
            # Names / indices not in mapping default to array dtype.
            (
                {"column_dtypes": {"A": np.int8, "B": np.float32}},
                np.rec.array(
                    [("0", "1", "0.2", "a"), ("1", "2", "1.5", "bc")],
                    dtype=[
                        ("index", f"{tm.ENDIAN}i8"),
                        ("A", "i1"),
                        ("B", f"{tm.ENDIAN}f4"),
                        ("C", "O"),
                    ],
                ),
            ),
            # Names / indices not in dtype mapping default to array dtype.
            (
                {"column_dtypes": {"A": np.dtype("int8"), "B": np.dtype("float32")}},
                np.rec.array(
                    [("0", "1", "0.2", "a"), ("1", "2", "1.5", "bc")],
                    dtype=[
                        ("index", f"{tm.ENDIAN}i8"),
                        ("A", "i1"),
                        ("B", f"{tm.ENDIAN}f4"),
                        ("C", "O"),
                    ],
                ),
            ),
            # Mixture of everything.
            (
                {
                    "column_dtypes": {"A": np.int8, "B": np.float32},
                    "index_dtypes": f"{tm.ENDIAN}U2",
                },
                np.rec.array(
                    [("0", "1", "0.2", "a"), ("1", "2", "1.5", "bc")],
                    dtype=[
                        ("index", f"{tm.ENDIAN}U2"),
                        ("A", "i1"),
                        ("B", f"{tm.ENDIAN}f4"),
                        ("C", "O"),
                    ],
                ),
            ),
            # Invalid dype values.
            (
                {"index": False, "column_dtypes": []},
                (ValueError, "Invalid dtype \\[\\] specified for column A"),
            ),
            (
                {"index": False, "column_dtypes": {"A": "int32", "B": 5}},
                (ValueError, "Invalid dtype 5 specified for column B"),
            ),
            # Numpy can't handle EA types, so check error is raised
            (
                {
                    "index": False,
                    "column_dtypes": {"A": "int32", "B": CategoricalDtype(["a", "b"])},
                },
                (ValueError, "Invalid dtype category specified for column B"),
            ),
            # Check that bad types raise
            (
                {"index": False, "column_dtypes": {"A": "int32", "B": "foo"}},
                (TypeError, "data type [\"']foo[\"'] not understood"),
            ),
        ],
    )
    def test_to_records_dtype(self, kwargs, expected):
        # see GH#18146
        df = DataFrame({"A": [1, 2], "B": [0.2, 1.5], "C": ["a", "bc"]})

        if not isinstance(expected, np.rec.recarray):
            with pytest.raises(expected[0], match=expected[1]):
                df.to_records(**kwargs)
        else:
            result = df.to_records(**kwargs)
            tm.assert_almost_equal(result, expected)

    @pytest.mark.parametrize(
        "df,kwargs,expected",
        [
            # MultiIndex in the index.
            (
                DataFrame(
                    [[1, 2, 3], [4, 5, 6], [7, 8, 9]], columns=list("abc")
                ).set_index(["a", "b"]),
                {"column_dtypes": "float64", "index_dtypes": {0: "int32", 1: "int8"}},
                np.rec.array(
                    [(1, 2, 3.0), (4, 5, 6.0), (7, 8, 9.0)],
                    dtype=[
                        ("a", f"{tm.ENDIAN}i4"),
                        ("b", "i1"),
                        ("c", f"{tm.ENDIAN}f8"),
                    ],
                ),
            ),
            # MultiIndex in the columns.
            (
                DataFrame(
                    [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
                    columns=MultiIndex.from_tuples(
                        [("a", "d"), ("b", "e"), ("c", "f")]
                    ),
                ),
                {
                    "column_dtypes": {0: f"{tm.ENDIAN}U1", 2: "float32"},
                    "index_dtypes": "float32",
                },
                np.rec.array(
                    [(0.0, "1", 2, 3.0), (1.0, "4", 5, 6.0), (2.0, "7", 8, 9.0)],
                    dtype=[
                        ("index", f"{tm.ENDIAN}f4"),
                        ("('a', 'd')", f"{tm.ENDIAN}U1"),
                        ("('b', 'e')", f"{tm.ENDIAN}i8"),
                        ("('c', 'f')", f"{tm.ENDIAN}f4"),
                    ],
                ),
            ),
            # MultiIndex in both the columns and index.
            (
                DataFrame(
                    [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
                    columns=MultiIndex.from_tuples(
                        [("a", "d"), ("b", "e"), ("c", "f")], names=list("ab")
                    ),
                    index=MultiIndex.from_tuples(
                        [("d", -4), ("d", -5), ("f", -6)], names=list("cd")
                    ),
                ),
                {
                    "column_dtypes": "float64",
                    "index_dtypes": {0: f"{tm.ENDIAN}U2", 1: "int8"},
                },
                np.rec.array(
                    [
                        ("d", -4, 1.0, 2.0, 3.0),
                        ("d", -5, 4.0, 5.0, 6.0),
                        ("f", -6, 7, 8, 9.0),
                    ],
                    dtype=[
                        ("c", f"{tm.ENDIAN}U2"),
                        ("d", "i1"),
                        ("('a', 'd')", f"{tm.ENDIAN}f8"),
                        ("('b', 'e')", f"{tm.ENDIAN}f8"),
                        ("('c', 'f')", f"{tm.ENDIAN}f8"),
                    ],
                ),
            ),
        ],
    )
    def test_to_records_dtype_mi(self, df, kwargs, expected):
        # see GH#18146
        result = df.to_records(**kwargs)
        tm.assert_almost_equal(result, expected)

    def test_to_records_dict_like(self):
        # see GH#18146
        class DictLike:
            def __init__(self, **kwargs) -> None:
                self.d = kwargs.copy()

            def __getitem__(self, key):
                return self.d.__getitem__(key)

            def __contains__(self, key) -> bool:
                return key in self.d

            def keys(self):
                return self.d.keys()

        df = DataFrame({"A": [1, 2], "B": [0.2, 1.5], "C": ["a", "bc"]})

        dtype_mappings = {
            "column_dtypes": DictLike(A=np.int8, B=np.float32),
            "index_dtypes": f"{tm.ENDIAN}U2",
        }

        result = df.to_records(**dtype_mappings)
        expected = np.rec.array(
            [("0", "1", "0.2", "a"), ("1", "2", "1.5", "bc")],
            dtype=[
                ("index", f"{tm.ENDIAN}U2"),
                ("A", "i1"),
                ("B", f"{tm.ENDIAN}f4"),
                ("C", "O"),
            ],
        )
        tm.assert_almost_equal(result, expected)

    @pytest.mark.parametrize("tz", ["UTC", "GMT", "US/Eastern"])
    def test_to_records_datetimeindex_with_tz(self, tz):
        # GH#13937
        dr = date_range("2016-01-01", periods=10, freq="s", tz=tz)

        df = DataFrame({"datetime": dr}, index=dr)

        expected = df.to_records()
        result = df.tz_convert("UTC").to_records()

        # both converted to UTC, so they are equal
        tm.assert_numpy_array_equal(result, expected)
