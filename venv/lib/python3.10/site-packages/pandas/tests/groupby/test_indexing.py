# Test GroupBy._positional_selector positional grouped indexing GH#42864

import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm


@pytest.mark.parametrize(
    "arg, expected_rows",
    [
        [0, [0, 1, 4]],
        [2, [5]],
        [5, []],
        [-1, [3, 4, 7]],
        [-2, [1, 6]],
        [-6, []],
    ],
)
def test_int(slice_test_df, slice_test_grouped, arg, expected_rows):
    # Test single integer
    result = slice_test_grouped._positional_selector[arg]
    expected = slice_test_df.iloc[expected_rows]

    tm.assert_frame_equal(result, expected)


def test_slice(slice_test_df, slice_test_grouped):
    # Test single slice
    result = slice_test_grouped._positional_selector[0:3:2]
    expected = slice_test_df.iloc[[0, 1, 4, 5]]

    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "arg, expected_rows",
    [
        [[0, 2], [0, 1, 4, 5]],
        [[0, 2, -1], [0, 1, 3, 4, 5, 7]],
        [range(0, 3, 2), [0, 1, 4, 5]],
        [{0, 2}, [0, 1, 4, 5]],
    ],
    ids=[
        "list",
        "negative",
        "range",
        "set",
    ],
)
def test_list(slice_test_df, slice_test_grouped, arg, expected_rows):
    # Test lists of integers and integer valued iterables
    result = slice_test_grouped._positional_selector[arg]
    expected = slice_test_df.iloc[expected_rows]

    tm.assert_frame_equal(result, expected)


def test_ints(slice_test_df, slice_test_grouped):
    # Test tuple of ints
    result = slice_test_grouped._positional_selector[0, 2, -1]
    expected = slice_test_df.iloc[[0, 1, 3, 4, 5, 7]]

    tm.assert_frame_equal(result, expected)


def test_slices(slice_test_df, slice_test_grouped):
    # Test tuple of slices
    result = slice_test_grouped._positional_selector[:2, -2:]
    expected = slice_test_df.iloc[[0, 1, 2, 3, 4, 6, 7]]

    tm.assert_frame_equal(result, expected)


def test_mix(slice_test_df, slice_test_grouped):
    # Test mixed tuple of ints and slices
    result = slice_test_grouped._positional_selector[0, 1, -2:]
    expected = slice_test_df.iloc[[0, 1, 2, 3, 4, 6, 7]]

    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "arg, expected_rows",
    [
        [0, [0, 1, 4]],
        [[0, 2, -1], [0, 1, 3, 4, 5, 7]],
        [(slice(None, 2), slice(-2, None)), [0, 1, 2, 3, 4, 6, 7]],
    ],
)
def test_as_index(slice_test_df, arg, expected_rows):
    # Test the default as_index behaviour
    result = slice_test_df.groupby("Group", sort=False)._positional_selector[arg]
    expected = slice_test_df.iloc[expected_rows]

    tm.assert_frame_equal(result, expected)


def test_doc_examples():
    # Test the examples in the documentation
    df = pd.DataFrame(
        [["a", 1], ["a", 2], ["a", 3], ["b", 4], ["b", 5]], columns=["A", "B"]
    )

    grouped = df.groupby("A", as_index=False)

    result = grouped._positional_selector[1:2]
    expected = pd.DataFrame([["a", 2], ["b", 5]], columns=["A", "B"], index=[1, 4])

    tm.assert_frame_equal(result, expected)

    result = grouped._positional_selector[1, -1]
    expected = pd.DataFrame(
        [["a", 2], ["a", 3], ["b", 5]], columns=["A", "B"], index=[1, 2, 4]
    )

    tm.assert_frame_equal(result, expected)


@pytest.fixture()
def multiindex_data():
    rng = np.random.default_rng(2)
    ndates = 100
    nitems = 20
    dates = pd.date_range("20130101", periods=ndates, freq="D")
    items = [f"item {i}" for i in range(nitems)]

    data = {}
    for date in dates:
        nitems_for_date = nitems - rng.integers(0, 12)
        levels = [
            (item, rng.integers(0, 10000) / 100, rng.integers(0, 10000) / 100)
            for item in items[:nitems_for_date]
        ]
        levels.sort(key=lambda x: x[1])
        data[date] = levels

    return data


def _make_df_from_data(data):
    rows = {}
    for date in data:
        for level in data[date]:
            rows[(date, level[0])] = {"A": level[1], "B": level[2]}

    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index.names = ("Date", "Item")
    return df


def test_multiindex(multiindex_data):
    # Test the multiindex mentioned as the use-case in the documentation
    df = _make_df_from_data(multiindex_data)
    result = df.groupby("Date", as_index=False).nth(slice(3, -3))

    sliced = {date: multiindex_data[date][3:-3] for date in multiindex_data}
    expected = _make_df_from_data(sliced)

    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("arg", [1, 5, 30, 1000, -1, -5, -30, -1000])
@pytest.mark.parametrize("method", ["head", "tail"])
@pytest.mark.parametrize("simulated", [True, False])
def test_against_head_and_tail(arg, method, simulated):
    # Test gives the same results as grouped head and tail
    n_groups = 100
    n_rows_per_group = 30

    data = {
        "group": [
            f"group {g}" for j in range(n_rows_per_group) for g in range(n_groups)
        ],
        "value": [
            f"group {g} row {j}"
            for j in range(n_rows_per_group)
            for g in range(n_groups)
        ],
    }
    df = pd.DataFrame(data)
    grouped = df.groupby("group", as_index=False)
    size = arg if arg >= 0 else n_rows_per_group + arg

    if method == "head":
        result = grouped._positional_selector[:arg]

        if simulated:
            indices = [
                j * n_groups + i
                for j in range(size)
                for i in range(n_groups)
                if j * n_groups + i < n_groups * n_rows_per_group
            ]
            expected = df.iloc[indices]

        else:
            expected = grouped.head(arg)

    else:
        result = grouped._positional_selector[-arg:]

        if simulated:
            indices = [
                (n_rows_per_group + j - size) * n_groups + i
                for j in range(size)
                for i in range(n_groups)
                if (n_rows_per_group + j - size) * n_groups + i >= 0
            ]
            expected = df.iloc[indices]

        else:
            expected = grouped.tail(arg)

    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("start", [None, 0, 1, 10, -1, -10])
@pytest.mark.parametrize("stop", [None, 0, 1, 10, -1, -10])
@pytest.mark.parametrize("step", [None, 1, 5])
def test_against_df_iloc(start, stop, step):
    # Test that a single group gives the same results as DataFrame.iloc
    n_rows = 30

    data = {
        "group": ["group 0"] * n_rows,
        "value": list(range(n_rows)),
    }
    df = pd.DataFrame(data)
    grouped = df.groupby("group", as_index=False)

    result = grouped._positional_selector[start:stop:step]
    expected = df.iloc[start:stop:step]

    tm.assert_frame_equal(result, expected)


def test_series():
    # Test grouped Series
    ser = pd.Series([1, 2, 3, 4, 5], index=["a", "a", "a", "b", "b"])
    grouped = ser.groupby(level=0)
    result = grouped._positional_selector[1:2]
    expected = pd.Series([2, 5], index=["a", "b"])

    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("step", [1, 2, 3, 4, 5])
def test_step(step):
    # Test slice with various step values
    data = [["x", f"x{i}"] for i in range(5)]
    data += [["y", f"y{i}"] for i in range(4)]
    data += [["z", f"z{i}"] for i in range(3)]
    df = pd.DataFrame(data, columns=["A", "B"])

    grouped = df.groupby("A", as_index=False)

    result = grouped._positional_selector[::step]

    data = [["x", f"x{i}"] for i in range(0, 5, step)]
    data += [["y", f"y{i}"] for i in range(0, 4, step)]
    data += [["z", f"z{i}"] for i in range(0, 3, step)]

    index = [0 + i for i in range(0, 5, step)]
    index += [5 + i for i in range(0, 4, step)]
    index += [9 + i for i in range(0, 3, step)]

    expected = pd.DataFrame(data, columns=["A", "B"], index=index)

    tm.assert_frame_equal(result, expected)


@pytest.fixture()
def column_group_df():
    return pd.DataFrame(
        [[0, 1, 2, 3, 4, 5, 6], [0, 0, 1, 0, 1, 0, 2]],
        columns=["A", "B", "C", "D", "E", "F", "G"],
    )


def test_column_axis(column_group_df):
    msg = "DataFrame.groupby with axis=1"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        g = column_group_df.groupby(column_group_df.iloc[1], axis=1)
    result = g._positional_selector[1:-1]
    expected = column_group_df.iloc[:, [1, 3]]

    tm.assert_frame_equal(result, expected)


def test_columns_on_iter():
    # GitHub issue #44821
    df = pd.DataFrame({k: range(10) for k in "ABC"})

    # Group-by and select columns
    cols = ["A", "B"]
    for _, dg in df.groupby(df.A < 4)[cols]:
        tm.assert_index_equal(dg.columns, pd.Index(cols))
        assert "C" not in dg.columns


@pytest.mark.parametrize("func", [list, pd.Index, pd.Series, np.array])
def test_groupby_duplicated_columns(func):
    # GH#44924
    df = pd.DataFrame(
        {
            "A": [1, 2],
            "B": [3, 3],
            "C": ["G", "G"],
        }
    )
    result = df.groupby("C")[func(["A", "B", "A"])].mean()
    expected = pd.DataFrame(
        [[1.5, 3.0, 1.5]], columns=["A", "B", "A"], index=pd.Index(["G"], name="C")
    )
    tm.assert_frame_equal(result, expected)


def test_groupby_get_nonexisting_groups():
    # GH#32492
    df = pd.DataFrame(
        data={
            "A": ["a1", "a2", None],
            "B": ["b1", "b2", "b1"],
            "val": [1, 2, 3],
        }
    )
    grps = df.groupby(by=["A", "B"])

    msg = "('a2', 'b1')"
    with pytest.raises(KeyError, match=msg):
        grps.get_group(("a2", "b1"))
