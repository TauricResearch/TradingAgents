import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm


@pytest.fixture(params=[["inner"], ["inner", "outer"]])
def frame(request):
    levels = request.param
    df = pd.DataFrame(
        {
            "outer": ["a", "a", "a", "b", "b", "b"],
            "inner": [1, 2, 3, 1, 2, 3],
            "A": np.arange(6),
            "B": ["one", "one", "two", "two", "one", "one"],
        }
    )
    if levels:
        df = df.set_index(levels)

    return df


@pytest.fixture()
def series():
    df = pd.DataFrame(
        {
            "outer": ["a", "a", "a", "b", "b", "b"],
            "inner": [1, 2, 3, 1, 2, 3],
            "A": np.arange(6),
            "B": ["one", "one", "two", "two", "one", "one"],
        }
    )
    s = df.set_index(["outer", "inner", "B"])["A"]

    return s


@pytest.mark.parametrize(
    "key_strs,groupers",
    [
        ("inner", pd.Grouper(level="inner")),  # Index name
        (["inner"], [pd.Grouper(level="inner")]),  # List of index name
        (["B", "inner"], ["B", pd.Grouper(level="inner")]),  # Column and index
        (["inner", "B"], [pd.Grouper(level="inner"), "B"]),  # Index and column
    ],
)
def test_grouper_index_level_as_string(frame, key_strs, groupers):
    if "B" not in key_strs or "outer" in frame.columns:
        result = frame.groupby(key_strs).mean(numeric_only=True)
        expected = frame.groupby(groupers).mean(numeric_only=True)
    else:
        result = frame.groupby(key_strs).mean()
        expected = frame.groupby(groupers).mean()
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "levels",
    [
        "inner",
        "outer",
        "B",
        ["inner"],
        ["outer"],
        ["B"],
        ["inner", "outer"],
        ["outer", "inner"],
        ["inner", "outer", "B"],
        ["B", "outer", "inner"],
    ],
)
def test_grouper_index_level_as_string_series(series, levels):
    # Compute expected result
    if isinstance(levels, list):
        groupers = [pd.Grouper(level=lv) for lv in levels]
    else:
        groupers = pd.Grouper(level=levels)

    expected = series.groupby(groupers).mean()

    # Compute and check result
    result = series.groupby(levels).mean()
    tm.assert_series_equal(result, expected)
