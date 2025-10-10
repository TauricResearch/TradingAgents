import re

import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm


def test_error():
    df = pd.DataFrame(
        {"A": pd.Series([[0, 1, 2], np.nan, [], (3, 4)], index=list("abcd")), "B": 1}
    )
    with pytest.raises(
        ValueError, match="column must be a scalar, tuple, or list thereof"
    ):
        df.explode([list("AA")])

    with pytest.raises(ValueError, match="column must be unique"):
        df.explode(list("AA"))

    df.columns = list("AA")
    with pytest.raises(
        ValueError,
        match=re.escape("DataFrame columns must be unique. Duplicate columns: ['A']"),
    ):
        df.explode("A")


@pytest.mark.parametrize(
    "input_subset, error_message",
    [
        (
            list("AC"),
            "columns must have matching element counts",
        ),
        (
            [],
            "column must be nonempty",
        ),
        (
            list("AC"),
            "columns must have matching element counts",
        ),
    ],
)
def test_error_multi_columns(input_subset, error_message):
    # GH 39240
    df = pd.DataFrame(
        {
            "A": [[0, 1, 2], np.nan, [], (3, 4)],
            "B": 1,
            "C": [["a", "b", "c"], "foo", [], ["d", "e", "f"]],
        },
        index=list("abcd"),
    )
    with pytest.raises(ValueError, match=error_message):
        df.explode(input_subset)


@pytest.mark.parametrize(
    "scalar",
    ["a", 0, 1.5, pd.Timedelta("1 days"), pd.Timestamp("2019-12-31")],
)
def test_basic(scalar):
    df = pd.DataFrame(
        {scalar: pd.Series([[0, 1, 2], np.nan, [], (3, 4)], index=list("abcd")), "B": 1}
    )
    result = df.explode(scalar)
    expected = pd.DataFrame(
        {
            scalar: pd.Series(
                [0, 1, 2, np.nan, np.nan, 3, 4], index=list("aaabcdd"), dtype=object
            ),
            "B": 1,
        }
    )
    tm.assert_frame_equal(result, expected)


def test_multi_index_rows():
    df = pd.DataFrame(
        {"A": np.array([[0, 1, 2], np.nan, [], (3, 4)], dtype=object), "B": 1},
        index=pd.MultiIndex.from_tuples([("a", 1), ("a", 2), ("b", 1), ("b", 2)]),
    )

    result = df.explode("A")
    expected = pd.DataFrame(
        {
            "A": pd.Series(
                [0, 1, 2, np.nan, np.nan, 3, 4],
                index=pd.MultiIndex.from_tuples(
                    [
                        ("a", 1),
                        ("a", 1),
                        ("a", 1),
                        ("a", 2),
                        ("b", 1),
                        ("b", 2),
                        ("b", 2),
                    ]
                ),
                dtype=object,
            ),
            "B": 1,
        }
    )
    tm.assert_frame_equal(result, expected)


def test_multi_index_columns():
    df = pd.DataFrame(
        {("A", 1): np.array([[0, 1, 2], np.nan, [], (3, 4)], dtype=object), ("A", 2): 1}
    )

    result = df.explode(("A", 1))
    expected = pd.DataFrame(
        {
            ("A", 1): pd.Series(
                [0, 1, 2, np.nan, np.nan, 3, 4],
                index=pd.Index([0, 0, 0, 1, 2, 3, 3]),
                dtype=object,
            ),
            ("A", 2): 1,
        }
    )
    tm.assert_frame_equal(result, expected)


def test_usecase():
    # explode a single column
    # gh-10511
    df = pd.DataFrame(
        [[11, range(5), 10], [22, range(3), 20]], columns=list("ABC")
    ).set_index("C")
    result = df.explode("B")

    expected = pd.DataFrame(
        {
            "A": [11, 11, 11, 11, 11, 22, 22, 22],
            "B": np.array([0, 1, 2, 3, 4, 0, 1, 2], dtype=object),
            "C": [10, 10, 10, 10, 10, 20, 20, 20],
        },
        columns=list("ABC"),
    ).set_index("C")

    tm.assert_frame_equal(result, expected)

    # gh-8517
    df = pd.DataFrame(
        [["2014-01-01", "Alice", "A B"], ["2014-01-02", "Bob", "C D"]],
        columns=["dt", "name", "text"],
    )
    result = df.assign(text=df.text.str.split(" ")).explode("text")
    expected = pd.DataFrame(
        [
            ["2014-01-01", "Alice", "A"],
            ["2014-01-01", "Alice", "B"],
            ["2014-01-02", "Bob", "C"],
            ["2014-01-02", "Bob", "D"],
        ],
        columns=["dt", "name", "text"],
        index=[0, 0, 1, 1],
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "input_dict, input_index, expected_dict, expected_index",
    [
        (
            {"col1": [[1, 2], [3, 4]], "col2": ["foo", "bar"]},
            [0, 0],
            {"col1": [1, 2, 3, 4], "col2": ["foo", "foo", "bar", "bar"]},
            [0, 0, 0, 0],
        ),
        (
            {"col1": [[1, 2], [3, 4]], "col2": ["foo", "bar"]},
            pd.Index([0, 0], name="my_index"),
            {"col1": [1, 2, 3, 4], "col2": ["foo", "foo", "bar", "bar"]},
            pd.Index([0, 0, 0, 0], name="my_index"),
        ),
        (
            {"col1": [[1, 2], [3, 4]], "col2": ["foo", "bar"]},
            pd.MultiIndex.from_arrays(
                [[0, 0], [1, 1]], names=["my_first_index", "my_second_index"]
            ),
            {"col1": [1, 2, 3, 4], "col2": ["foo", "foo", "bar", "bar"]},
            pd.MultiIndex.from_arrays(
                [[0, 0, 0, 0], [1, 1, 1, 1]],
                names=["my_first_index", "my_second_index"],
            ),
        ),
        (
            {"col1": [[1, 2], [3, 4]], "col2": ["foo", "bar"]},
            pd.MultiIndex.from_arrays([[0, 0], [1, 1]], names=["my_index", None]),
            {"col1": [1, 2, 3, 4], "col2": ["foo", "foo", "bar", "bar"]},
            pd.MultiIndex.from_arrays(
                [[0, 0, 0, 0], [1, 1, 1, 1]], names=["my_index", None]
            ),
        ),
    ],
)
def test_duplicate_index(input_dict, input_index, expected_dict, expected_index):
    # GH 28005
    df = pd.DataFrame(input_dict, index=input_index, dtype=object)
    result = df.explode("col1")
    expected = pd.DataFrame(expected_dict, index=expected_index, dtype=object)
    tm.assert_frame_equal(result, expected)


def test_ignore_index():
    # GH 34932
    df = pd.DataFrame({"id": range(0, 20, 10), "values": [list("ab"), list("cd")]})
    result = df.explode("values", ignore_index=True)
    expected = pd.DataFrame(
        {"id": [0, 0, 10, 10], "values": list("abcd")}, index=[0, 1, 2, 3]
    )
    tm.assert_frame_equal(result, expected)


def test_explode_sets():
    # https://github.com/pandas-dev/pandas/issues/35614
    df = pd.DataFrame({"a": [{"x", "y"}], "b": [1]}, index=[1])
    result = df.explode(column="a").sort_values(by="a")
    expected = pd.DataFrame({"a": ["x", "y"], "b": [1, 1]}, index=[1, 1])
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "input_subset, expected_dict, expected_index",
    [
        (
            list("AC"),
            {
                "A": pd.Series(
                    [0, 1, 2, np.nan, np.nan, 3, 4, np.nan],
                    index=list("aaabcdde"),
                    dtype=object,
                ),
                "B": 1,
                "C": ["a", "b", "c", "foo", np.nan, "d", "e", np.nan],
            },
            list("aaabcdde"),
        ),
        (
            list("A"),
            {
                "A": pd.Series(
                    [0, 1, 2, np.nan, np.nan, 3, 4, np.nan],
                    index=list("aaabcdde"),
                    dtype=object,
                ),
                "B": 1,
                "C": [
                    ["a", "b", "c"],
                    ["a", "b", "c"],
                    ["a", "b", "c"],
                    "foo",
                    [],
                    ["d", "e"],
                    ["d", "e"],
                    np.nan,
                ],
            },
            list("aaabcdde"),
        ),
    ],
)
def test_multi_columns(input_subset, expected_dict, expected_index):
    # GH 39240
    df = pd.DataFrame(
        {
            "A": [[0, 1, 2], np.nan, [], (3, 4), np.nan],
            "B": 1,
            "C": [["a", "b", "c"], "foo", [], ["d", "e"], np.nan],
        },
        index=list("abcde"),
    )
    result = df.explode(input_subset)
    expected = pd.DataFrame(expected_dict, expected_index)
    tm.assert_frame_equal(result, expected)


def test_multi_columns_nan_empty():
    # GH 46084
    df = pd.DataFrame(
        {
            "A": [[0, 1], [5], [], [2, 3]],
            "B": [9, 8, 7, 6],
            "C": [[1, 2], np.nan, [], [3, 4]],
        }
    )
    result = df.explode(["A", "C"])
    expected = pd.DataFrame(
        {
            "A": np.array([0, 1, 5, np.nan, 2, 3], dtype=object),
            "B": [9, 9, 8, 7, 6, 6],
            "C": np.array([1, 2, np.nan, np.nan, 3, 4], dtype=object),
        },
        index=[0, 0, 1, 2, 3, 3],
    )
    tm.assert_frame_equal(result, expected)


def test_str_dtype():
    # https://github.com/pandas-dev/pandas/pull/61623
    df = pd.DataFrame({"a": ["x", "y"]}, dtype="str")
    result = df.explode(column="a")
    assert result is not df
    tm.assert_frame_equal(result, df)
