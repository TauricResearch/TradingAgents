import numpy as np

import pandas as pd
import pandas._testing as tm


def test_group_by_copy():
    # GH#44803
    df = pd.DataFrame(
        {
            "name": ["Alice", "Bob", "Carl"],
            "age": [20, 21, 20],
        }
    ).set_index("name")

    msg = "DataFrameGroupBy.apply operated on the grouping columns"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        grp_by_same_value = df.groupby(["age"], group_keys=False).apply(
            lambda group: group
        )
    msg = "DataFrameGroupBy.apply operated on the grouping columns"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        grp_by_copy = df.groupby(["age"], group_keys=False).apply(
            lambda group: group.copy()
        )
    tm.assert_frame_equal(grp_by_same_value, grp_by_copy)


def test_mutate_groups():
    # GH3380

    df = pd.DataFrame(
        {
            "cat1": ["a"] * 8 + ["b"] * 6,
            "cat2": ["c"] * 2
            + ["d"] * 2
            + ["e"] * 2
            + ["f"] * 2
            + ["c"] * 2
            + ["d"] * 2
            + ["e"] * 2,
            "cat3": [f"g{x}" for x in range(1, 15)],
            "val": np.random.default_rng(2).integers(100, size=14),
        }
    )

    def f_copy(x):
        x = x.copy()
        x["rank"] = x.val.rank(method="min")
        return x.groupby("cat2")["rank"].min()

    def f_no_copy(x):
        x["rank"] = x.val.rank(method="min")
        return x.groupby("cat2")["rank"].min()

    msg = "DataFrameGroupBy.apply operated on the grouping columns"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        grpby_copy = df.groupby("cat1").apply(f_copy)
    with tm.assert_produces_warning(FutureWarning, match=msg):
        grpby_no_copy = df.groupby("cat1").apply(f_no_copy)
    tm.assert_series_equal(grpby_copy, grpby_no_copy)


def test_no_mutate_but_looks_like():
    # GH 8467
    # first show's mutation indicator
    # second does not, but should yield the same results
    df = pd.DataFrame({"key": [1, 1, 1, 2, 2, 2, 3, 3, 3], "value": range(9)})

    msg = "DataFrameGroupBy.apply operated on the grouping columns"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result1 = df.groupby("key", group_keys=True).apply(lambda x: x[:].key)
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result2 = df.groupby("key", group_keys=True).apply(lambda x: x.key)
    tm.assert_series_equal(result1, result2)


def test_apply_function_with_indexing(warn_copy_on_write):
    # GH: 33058
    df = pd.DataFrame(
        {"col1": ["A", "A", "A", "B", "B", "B"], "col2": [1, 2, 3, 4, 5, 6]}
    )

    def fn(x):
        x.loc[x.index[-1], "col2"] = 0
        return x.col2

    msg = "DataFrameGroupBy.apply operated on the grouping columns"
    with tm.assert_produces_warning(
        FutureWarning, match=msg, raise_on_extra_warnings=not warn_copy_on_write
    ):
        result = df.groupby(["col1"], as_index=False).apply(fn)
    expected = pd.Series(
        [1, 2, 0, 4, 5, 0],
        index=pd.MultiIndex.from_tuples(
            [(0, 0), (0, 1), (0, 2), (1, 3), (1, 4), (1, 5)]
        ),
        name="col2",
    )
    tm.assert_series_equal(result, expected)


def test_apply_mutate_columns_multiindex():
    # GH 12652
    df = pd.DataFrame(
        {
            ("C", "julian"): [1, 2, 3],
            ("B", "geoffrey"): [1, 2, 3],
            ("A", "julian"): [1, 2, 3],
            ("B", "julian"): [1, 2, 3],
            ("A", "geoffrey"): [1, 2, 3],
            ("C", "geoffrey"): [1, 2, 3],
        },
        columns=pd.MultiIndex.from_tuples(
            [
                ("A", "julian"),
                ("A", "geoffrey"),
                ("B", "julian"),
                ("B", "geoffrey"),
                ("C", "julian"),
                ("C", "geoffrey"),
            ]
        ),
    )

    def add_column(grouped):
        name = grouped.columns[0][1]
        grouped["sum", name] = grouped.sum(axis=1)
        return grouped

    msg = "DataFrame.groupby with axis=1 is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        gb = df.groupby(level=1, axis=1)
    result = gb.apply(add_column)
    expected = pd.DataFrame(
        [
            [1, 1, 1, 3, 1, 1, 1, 3],
            [2, 2, 2, 6, 2, 2, 2, 6],
            [
                3,
                3,
                3,
                9,
                3,
                3,
                3,
                9,
            ],
        ],
        columns=pd.MultiIndex.from_tuples(
            [
                ("geoffrey", "A", "geoffrey"),
                ("geoffrey", "B", "geoffrey"),
                ("geoffrey", "C", "geoffrey"),
                ("geoffrey", "sum", "geoffrey"),
                ("julian", "A", "julian"),
                ("julian", "B", "julian"),
                ("julian", "C", "julian"),
                ("julian", "sum", "julian"),
            ]
        ),
    )
    tm.assert_frame_equal(result, expected)
