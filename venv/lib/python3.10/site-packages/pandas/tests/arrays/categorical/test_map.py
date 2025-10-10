import numpy as np
import pytest

import pandas as pd
from pandas import (
    Categorical,
    Index,
    Series,
)
import pandas._testing as tm


@pytest.fixture(params=[None, "ignore"])
def na_action(request):
    return request.param


@pytest.mark.parametrize(
    "data, categories",
    [
        (list("abcbca"), list("cab")),
        (pd.interval_range(0, 3).repeat(3), pd.interval_range(0, 3)),
    ],
    ids=["string", "interval"],
)
def test_map_str(data, categories, ordered, na_action):
    # GH 31202 - override base class since we want to maintain categorical/ordered
    cat = Categorical(data, categories=categories, ordered=ordered)
    result = cat.map(str, na_action=na_action)
    expected = Categorical(
        map(str, data), categories=map(str, categories), ordered=ordered
    )
    tm.assert_categorical_equal(result, expected)


def test_map(na_action):
    cat = Categorical(list("ABABC"), categories=list("CBA"), ordered=True)
    result = cat.map(lambda x: x.lower(), na_action=na_action)
    exp = Categorical(list("ababc"), categories=list("cba"), ordered=True)
    tm.assert_categorical_equal(result, exp)

    cat = Categorical(list("ABABC"), categories=list("BAC"), ordered=False)
    result = cat.map(lambda x: x.lower(), na_action=na_action)
    exp = Categorical(list("ababc"), categories=list("bac"), ordered=False)
    tm.assert_categorical_equal(result, exp)

    # GH 12766: Return an index not an array
    result = cat.map(lambda x: 1, na_action=na_action)
    exp = Index(np.array([1] * 5, dtype=np.int64))
    tm.assert_index_equal(result, exp)

    # change categories dtype
    cat = Categorical(list("ABABC"), categories=list("BAC"), ordered=False)

    def f(x):
        return {"A": 10, "B": 20, "C": 30}.get(x)

    result = cat.map(f, na_action=na_action)
    exp = Categorical([10, 20, 10, 20, 30], categories=[20, 10, 30], ordered=False)
    tm.assert_categorical_equal(result, exp)

    mapper = Series([10, 20, 30], index=["A", "B", "C"])
    result = cat.map(mapper, na_action=na_action)
    tm.assert_categorical_equal(result, exp)

    result = cat.map({"A": 10, "B": 20, "C": 30}, na_action=na_action)
    tm.assert_categorical_equal(result, exp)


@pytest.mark.parametrize(
    ("data", "f", "expected"),
    (
        ([1, 1, np.nan], pd.isna, Index([False, False, True])),
        ([1, 2, np.nan], pd.isna, Index([False, False, True])),
        ([1, 1, np.nan], {1: False}, Categorical([False, False, np.nan])),
        ([1, 2, np.nan], {1: False, 2: False}, Index([False, False, np.nan])),
        (
            [1, 1, np.nan],
            Series([False, False]),
            Categorical([False, False, np.nan]),
        ),
        (
            [1, 2, np.nan],
            Series([False] * 3),
            Index([False, False, np.nan]),
        ),
    ),
)
def test_map_with_nan_none(data, f, expected):  # GH 24241
    values = Categorical(data)
    result = values.map(f, na_action=None)
    if isinstance(expected, Categorical):
        tm.assert_categorical_equal(result, expected)
    else:
        tm.assert_index_equal(result, expected)


@pytest.mark.parametrize(
    ("data", "f", "expected"),
    (
        ([1, 1, np.nan], pd.isna, Categorical([False, False, np.nan])),
        ([1, 2, np.nan], pd.isna, Index([False, False, np.nan])),
        ([1, 1, np.nan], {1: False}, Categorical([False, False, np.nan])),
        ([1, 2, np.nan], {1: False, 2: False}, Index([False, False, np.nan])),
        (
            [1, 1, np.nan],
            Series([False, False]),
            Categorical([False, False, np.nan]),
        ),
        (
            [1, 2, np.nan],
            Series([False, False, False]),
            Index([False, False, np.nan]),
        ),
    ),
)
def test_map_with_nan_ignore(data, f, expected):  # GH 24241
    values = Categorical(data)
    result = values.map(f, na_action="ignore")
    if data[1] == 1:
        tm.assert_categorical_equal(result, expected)
    else:
        tm.assert_index_equal(result, expected)


def test_map_with_dict_or_series(na_action):
    orig_values = ["a", "B", 1, "a"]
    new_values = ["one", 2, 3.0, "one"]
    cat = Categorical(orig_values)

    mapper = Series(new_values[:-1], index=orig_values[:-1])
    result = cat.map(mapper, na_action=na_action)

    # Order of categories in result can be different
    expected = Categorical(new_values, categories=[3.0, 2, "one"])
    tm.assert_categorical_equal(result, expected)

    mapper = dict(zip(orig_values[:-1], new_values[:-1]))
    result = cat.map(mapper, na_action=na_action)
    # Order of categories in result can be different
    tm.assert_categorical_equal(result, expected)


def test_map_na_action_no_default_deprecated():
    # GH51645
    cat = Categorical(["a", "b", "c"])
    msg = (
        "The default value of 'ignore' for the `na_action` parameter in "
        "pandas.Categorical.map is deprecated and will be "
        "changed to 'None' in a future version. Please set na_action to the "
        "desired value to avoid seeing this warning"
    )
    with tm.assert_produces_warning(FutureWarning, match=msg):
        cat.map(lambda x: x)
