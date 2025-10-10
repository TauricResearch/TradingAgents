import numpy as np
import pytest

from pandas import (
    DataFrame,
    Series,
    from_dummies,
    get_dummies,
)
import pandas._testing as tm


@pytest.fixture
def dummies_basic():
    return DataFrame(
        {
            "col1_a": [1, 0, 1],
            "col1_b": [0, 1, 0],
            "col2_a": [0, 1, 0],
            "col2_b": [1, 0, 0],
            "col2_c": [0, 0, 1],
        },
    )


@pytest.fixture
def dummies_with_unassigned():
    return DataFrame(
        {
            "col1_a": [1, 0, 0],
            "col1_b": [0, 1, 0],
            "col2_a": [0, 1, 0],
            "col2_b": [0, 0, 0],
            "col2_c": [0, 0, 1],
        },
    )


def test_error_wrong_data_type():
    dummies = [0, 1, 0]
    with pytest.raises(
        TypeError,
        match=r"Expected 'data' to be a 'DataFrame'; Received 'data' of type: list",
    ):
        from_dummies(dummies)


def test_error_no_prefix_contains_unassigned():
    dummies = DataFrame({"a": [1, 0, 0], "b": [0, 1, 0]})
    with pytest.raises(
        ValueError,
        match=(
            r"Dummy DataFrame contains unassigned value\(s\); "
            r"First instance in row: 2"
        ),
    ):
        from_dummies(dummies)


def test_error_no_prefix_wrong_default_category_type():
    dummies = DataFrame({"a": [1, 0, 1], "b": [0, 1, 1]})
    with pytest.raises(
        TypeError,
        match=(
            r"Expected 'default_category' to be of type 'None', 'Hashable', or 'dict'; "
            r"Received 'default_category' of type: list"
        ),
    ):
        from_dummies(dummies, default_category=["c", "d"])


def test_error_no_prefix_multi_assignment():
    dummies = DataFrame({"a": [1, 0, 1], "b": [0, 1, 1]})
    with pytest.raises(
        ValueError,
        match=(
            r"Dummy DataFrame contains multi-assignment\(s\); "
            r"First instance in row: 2"
        ),
    ):
        from_dummies(dummies)


def test_error_no_prefix_contains_nan():
    dummies = DataFrame({"a": [1, 0, 0], "b": [0, 1, np.nan]})
    with pytest.raises(
        ValueError, match=r"Dummy DataFrame contains NA value in column: 'b'"
    ):
        from_dummies(dummies)


def test_error_contains_non_dummies():
    dummies = DataFrame(
        {"a": [1, 6, 3, 1], "b": [0, 1, 0, 2], "c": ["c1", "c2", "c3", "c4"]}
    )
    with pytest.raises(
        TypeError,
        match=r"Passed DataFrame contains non-dummy data",
    ):
        from_dummies(dummies)


def test_error_with_prefix_multiple_seperators():
    dummies = DataFrame(
        {
            "col1_a": [1, 0, 1],
            "col1_b": [0, 1, 0],
            "col2-a": [0, 1, 0],
            "col2-b": [1, 0, 1],
        },
    )
    with pytest.raises(
        ValueError,
        match=(r"Separator not specified for column: col2-a"),
    ):
        from_dummies(dummies, sep="_")


def test_error_with_prefix_sep_wrong_type(dummies_basic):
    with pytest.raises(
        TypeError,
        match=(
            r"Expected 'sep' to be of type 'str' or 'None'; "
            r"Received 'sep' of type: list"
        ),
    ):
        from_dummies(dummies_basic, sep=["_"])


def test_error_with_prefix_contains_unassigned(dummies_with_unassigned):
    with pytest.raises(
        ValueError,
        match=(
            r"Dummy DataFrame contains unassigned value\(s\); "
            r"First instance in row: 2"
        ),
    ):
        from_dummies(dummies_with_unassigned, sep="_")


def test_error_with_prefix_default_category_wrong_type(dummies_with_unassigned):
    with pytest.raises(
        TypeError,
        match=(
            r"Expected 'default_category' to be of type 'None', 'Hashable', or 'dict'; "
            r"Received 'default_category' of type: list"
        ),
    ):
        from_dummies(dummies_with_unassigned, sep="_", default_category=["x", "y"])


def test_error_with_prefix_default_category_dict_not_complete(
    dummies_with_unassigned,
):
    with pytest.raises(
        ValueError,
        match=(
            r"Length of 'default_category' \(1\) did not match "
            r"the length of the columns being encoded \(2\)"
        ),
    ):
        from_dummies(dummies_with_unassigned, sep="_", default_category={"col1": "x"})


def test_error_with_prefix_contains_nan(dummies_basic):
    # Set float64 dtype to avoid upcast when setting np.nan
    dummies_basic["col2_c"] = dummies_basic["col2_c"].astype("float64")
    dummies_basic.loc[2, "col2_c"] = np.nan
    with pytest.raises(
        ValueError, match=r"Dummy DataFrame contains NA value in column: 'col2_c'"
    ):
        from_dummies(dummies_basic, sep="_")


def test_error_with_prefix_contains_non_dummies(dummies_basic):
    # Set object dtype to avoid upcast when setting "str"
    dummies_basic["col2_c"] = dummies_basic["col2_c"].astype(object)
    dummies_basic.loc[2, "col2_c"] = "str"
    with pytest.raises(TypeError, match=r"Passed DataFrame contains non-dummy data"):
        from_dummies(dummies_basic, sep="_")


def test_error_with_prefix_double_assignment():
    dummies = DataFrame(
        {
            "col1_a": [1, 0, 1],
            "col1_b": [1, 1, 0],
            "col2_a": [0, 1, 0],
            "col2_b": [1, 0, 0],
            "col2_c": [0, 0, 1],
        },
    )
    with pytest.raises(
        ValueError,
        match=(
            r"Dummy DataFrame contains multi-assignment\(s\); "
            r"First instance in row: 0"
        ),
    ):
        from_dummies(dummies, sep="_")


def test_roundtrip_series_to_dataframe():
    categories = Series(["a", "b", "c", "a"])
    dummies = get_dummies(categories)
    result = from_dummies(dummies)
    expected = DataFrame({"": ["a", "b", "c", "a"]})
    tm.assert_frame_equal(result, expected)


def test_roundtrip_single_column_dataframe():
    categories = DataFrame({"": ["a", "b", "c", "a"]})
    dummies = get_dummies(categories)
    result = from_dummies(dummies, sep="_")
    expected = categories
    tm.assert_frame_equal(result, expected)


def test_roundtrip_with_prefixes():
    categories = DataFrame({"col1": ["a", "b", "a"], "col2": ["b", "a", "c"]})
    dummies = get_dummies(categories)
    result = from_dummies(dummies, sep="_")
    expected = categories
    tm.assert_frame_equal(result, expected)


def test_no_prefix_string_cats_basic():
    dummies = DataFrame({"a": [1, 0, 0, 1], "b": [0, 1, 0, 0], "c": [0, 0, 1, 0]})
    expected = DataFrame({"": ["a", "b", "c", "a"]})
    result = from_dummies(dummies)
    tm.assert_frame_equal(result, expected)


def test_no_prefix_string_cats_basic_bool_values():
    dummies = DataFrame(
        {
            "a": [True, False, False, True],
            "b": [False, True, False, False],
            "c": [False, False, True, False],
        }
    )
    expected = DataFrame({"": ["a", "b", "c", "a"]})
    result = from_dummies(dummies)
    tm.assert_frame_equal(result, expected)


def test_no_prefix_string_cats_basic_mixed_bool_values():
    dummies = DataFrame(
        {"a": [1, 0, 0, 1], "b": [False, True, False, False], "c": [0, 0, 1, 0]}
    )
    expected = DataFrame({"": ["a", "b", "c", "a"]})
    result = from_dummies(dummies)
    tm.assert_frame_equal(result, expected)


def test_no_prefix_int_cats_basic():
    dummies = DataFrame(
        {1: [1, 0, 0, 0], 25: [0, 1, 0, 0], 2: [0, 0, 1, 0], 5: [0, 0, 0, 1]}
    )
    expected = DataFrame({"": [1, 25, 2, 5]})
    result = from_dummies(dummies)
    tm.assert_frame_equal(result, expected)


def test_no_prefix_float_cats_basic():
    dummies = DataFrame(
        {1.0: [1, 0, 0, 0], 25.0: [0, 1, 0, 0], 2.5: [0, 0, 1, 0], 5.84: [0, 0, 0, 1]}
    )
    expected = DataFrame({"": [1.0, 25.0, 2.5, 5.84]})
    result = from_dummies(dummies)
    tm.assert_frame_equal(result, expected)


def test_no_prefix_mixed_cats_basic():
    dummies = DataFrame(
        {
            1.23: [1, 0, 0, 0, 0],
            "c": [0, 1, 0, 0, 0],
            2: [0, 0, 1, 0, 0],
            False: [0, 0, 0, 1, 0],
            None: [0, 0, 0, 0, 1],
        }
    )
    expected = DataFrame({"": [1.23, "c", 2, False, None]}, dtype="object")
    result = from_dummies(dummies)
    tm.assert_frame_equal(result, expected)


def test_no_prefix_string_cats_contains_get_dummies_NaN_column():
    dummies = DataFrame({"a": [1, 0, 0], "b": [0, 1, 0], "NaN": [0, 0, 1]})
    expected = DataFrame({"": ["a", "b", "NaN"]})
    result = from_dummies(dummies)
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "default_category, expected",
    [
        pytest.param(
            "c",
            DataFrame({"": ["a", "b", "c"]}),
            id="default_category is a str",
        ),
        pytest.param(
            1,
            DataFrame({"": ["a", "b", 1]}),
            id="default_category is a int",
        ),
        pytest.param(
            1.25,
            DataFrame({"": ["a", "b", 1.25]}),
            id="default_category is a float",
        ),
        pytest.param(
            0,
            DataFrame({"": ["a", "b", 0]}),
            id="default_category is a 0",
        ),
        pytest.param(
            False,
            DataFrame({"": ["a", "b", False]}),
            id="default_category is a bool",
        ),
        pytest.param(
            (1, 2),
            DataFrame({"": ["a", "b", (1, 2)]}),
            id="default_category is a tuple",
        ),
    ],
)
def test_no_prefix_string_cats_default_category(
    default_category, expected, using_infer_string
):
    dummies = DataFrame({"a": [1, 0, 0], "b": [0, 1, 0]})
    result = from_dummies(dummies, default_category=default_category)
    if using_infer_string:
        expected[""] = expected[""].astype("str")
    tm.assert_frame_equal(result, expected)


def test_with_prefix_basic(dummies_basic):
    expected = DataFrame({"col1": ["a", "b", "a"], "col2": ["b", "a", "c"]})
    result = from_dummies(dummies_basic, sep="_")
    tm.assert_frame_equal(result, expected)


def test_with_prefix_contains_get_dummies_NaN_column():
    dummies = DataFrame(
        {
            "col1_a": [1, 0, 0],
            "col1_b": [0, 1, 0],
            "col1_NaN": [0, 0, 1],
            "col2_a": [0, 1, 0],
            "col2_b": [0, 0, 0],
            "col2_c": [0, 0, 1],
            "col2_NaN": [1, 0, 0],
        },
    )
    expected = DataFrame({"col1": ["a", "b", "NaN"], "col2": ["NaN", "a", "c"]})
    result = from_dummies(dummies, sep="_")
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "default_category, expected",
    [
        pytest.param(
            "x",
            DataFrame({"col1": ["a", "b", "x"], "col2": ["x", "a", "c"]}),
            id="default_category is a str",
        ),
        pytest.param(
            0,
            DataFrame({"col1": ["a", "b", 0], "col2": [0, "a", "c"]}),
            id="default_category is a 0",
        ),
        pytest.param(
            False,
            DataFrame({"col1": ["a", "b", False], "col2": [False, "a", "c"]}),
            id="default_category is a False",
        ),
        pytest.param(
            {"col2": 1, "col1": 2.5},
            DataFrame({"col1": ["a", "b", 2.5], "col2": [1, "a", "c"]}),
            id="default_category is a dict with int and float values",
        ),
        pytest.param(
            {"col2": None, "col1": False},
            DataFrame({"col1": ["a", "b", False], "col2": [None, "a", "c"]}),
            id="default_category is a dict with bool and None values",
        ),
        pytest.param(
            {"col2": (1, 2), "col1": [1.25, False]},
            DataFrame({"col1": ["a", "b", [1.25, False]], "col2": [(1, 2), "a", "c"]}),
            id="default_category is a dict with list and tuple values",
        ),
    ],
)
def test_with_prefix_default_category(
    dummies_with_unassigned, default_category, expected, using_infer_string
):
    result = from_dummies(
        dummies_with_unassigned, sep="_", default_category=default_category
    )
    if using_infer_string:
        expected = expected.astype("str")
    tm.assert_frame_equal(result, expected)


def test_ea_categories():
    # GH 54300
    df = DataFrame({"a": [1, 0, 0, 1], "b": [0, 1, 0, 0], "c": [0, 0, 1, 0]})
    df.columns = df.columns.astype("string[python]")
    result = from_dummies(df)
    expected = DataFrame({"": Series(list("abca"), dtype="string[python]")})
    tm.assert_frame_equal(result, expected)


def test_ea_categories_with_sep():
    # GH 54300
    df = DataFrame(
        {
            "col1_a": [1, 0, 1],
            "col1_b": [0, 1, 0],
            "col2_a": [0, 1, 0],
            "col2_b": [1, 0, 0],
            "col2_c": [0, 0, 1],
        }
    )
    df.columns = df.columns.astype("string[python]")
    result = from_dummies(df, sep="_")
    expected = DataFrame(
        {
            "col1": Series(list("aba"), dtype="string[python]"),
            "col2": Series(list("bac"), dtype="string[python]"),
        }
    )
    expected.columns = expected.columns.astype("string[python]")
    tm.assert_frame_equal(result, expected)


def test_maintain_original_index():
    # GH 54300
    df = DataFrame(
        {"a": [1, 0, 0, 1], "b": [0, 1, 0, 0], "c": [0, 0, 1, 0]}, index=list("abcd")
    )
    result = from_dummies(df)
    expected = DataFrame({"": list("abca")}, index=list("abcd"))
    tm.assert_frame_equal(result, expected)
