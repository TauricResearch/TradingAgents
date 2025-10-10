import numpy as np
import pytest

from pandas.compat.pyarrow import pa_version_under10p1

from pandas.core.dtypes.missing import na_value_for_dtype

import pandas as pd
import pandas._testing as tm
from pandas.tests.groupby import get_groupby_method_args


@pytest.mark.parametrize(
    "dropna, tuples, outputs",
    [
        (
            True,
            [["A", "B"], ["B", "A"]],
            {"c": [13.0, 123.23], "d": [13.0, 123.0], "e": [13.0, 1.0]},
        ),
        (
            False,
            [["A", "B"], ["A", np.nan], ["B", "A"]],
            {
                "c": [13.0, 12.3, 123.23],
                "d": [13.0, 233.0, 123.0],
                "e": [13.0, 12.0, 1.0],
            },
        ),
    ],
)
def test_groupby_dropna_multi_index_dataframe_nan_in_one_group(
    dropna, tuples, outputs, nulls_fixture
):
    # GH 3729 this is to test that NA is in one group
    df_list = [
        ["A", "B", 12, 12, 12],
        ["A", nulls_fixture, 12.3, 233.0, 12],
        ["B", "A", 123.23, 123, 1],
        ["A", "B", 1, 1, 1.0],
    ]
    df = pd.DataFrame(df_list, columns=["a", "b", "c", "d", "e"])
    grouped = df.groupby(["a", "b"], dropna=dropna).sum()

    mi = pd.MultiIndex.from_tuples(tuples, names=list("ab"))

    # Since right now, by default MI will drop NA from levels when we create MI
    # via `from_*`, so we need to add NA for level manually afterwards.
    if not dropna:
        mi = mi.set_levels(["A", "B", np.nan], level="b")
    expected = pd.DataFrame(outputs, index=mi)

    tm.assert_frame_equal(grouped, expected)


@pytest.mark.parametrize(
    "dropna, tuples, outputs",
    [
        (
            True,
            [["A", "B"], ["B", "A"]],
            {"c": [12.0, 123.23], "d": [12.0, 123.0], "e": [12.0, 1.0]},
        ),
        (
            False,
            [["A", "B"], ["A", np.nan], ["B", "A"], [np.nan, "B"]],
            {
                "c": [12.0, 13.3, 123.23, 1.0],
                "d": [12.0, 234.0, 123.0, 1.0],
                "e": [12.0, 13.0, 1.0, 1.0],
            },
        ),
    ],
)
def test_groupby_dropna_multi_index_dataframe_nan_in_two_groups(
    dropna, tuples, outputs, nulls_fixture, nulls_fixture2
):
    # GH 3729 this is to test that NA in different groups with different representations
    df_list = [
        ["A", "B", 12, 12, 12],
        ["A", nulls_fixture, 12.3, 233.0, 12],
        ["B", "A", 123.23, 123, 1],
        [nulls_fixture2, "B", 1, 1, 1.0],
        ["A", nulls_fixture2, 1, 1, 1.0],
    ]
    df = pd.DataFrame(df_list, columns=["a", "b", "c", "d", "e"])
    grouped = df.groupby(["a", "b"], dropna=dropna).sum()

    mi = pd.MultiIndex.from_tuples(tuples, names=list("ab"))

    # Since right now, by default MI will drop NA from levels when we create MI
    # via `from_*`, so we need to add NA for level manually afterwards.
    if not dropna:
        mi = mi.set_levels([["A", "B", np.nan], ["A", "B", np.nan]])
    expected = pd.DataFrame(outputs, index=mi)

    tm.assert_frame_equal(grouped, expected)


@pytest.mark.parametrize(
    "dropna, idx, outputs",
    [
        (True, ["A", "B"], {"b": [123.23, 13.0], "c": [123.0, 13.0], "d": [1.0, 13.0]}),
        (
            False,
            ["A", "B", np.nan],
            {
                "b": [123.23, 13.0, 12.3],
                "c": [123.0, 13.0, 233.0],
                "d": [1.0, 13.0, 12.0],
            },
        ),
    ],
)
def test_groupby_dropna_normal_index_dataframe(dropna, idx, outputs):
    # GH 3729
    df_list = [
        ["B", 12, 12, 12],
        [None, 12.3, 233.0, 12],
        ["A", 123.23, 123, 1],
        ["B", 1, 1, 1.0],
    ]
    df = pd.DataFrame(df_list, columns=["a", "b", "c", "d"])
    grouped = df.groupby("a", dropna=dropna).sum()

    expected = pd.DataFrame(outputs, index=pd.Index(idx, name="a"))

    tm.assert_frame_equal(grouped, expected)


@pytest.mark.parametrize(
    "dropna, idx, expected",
    [
        (True, ["a", "a", "b", np.nan], pd.Series([3, 3], index=["a", "b"])),
        (
            False,
            ["a", "a", "b", np.nan],
            pd.Series([3, 3, 3], index=["a", "b", np.nan]),
        ),
    ],
)
def test_groupby_dropna_series_level(dropna, idx, expected):
    ser = pd.Series([1, 2, 3, 3], index=idx)

    result = ser.groupby(level=0, dropna=dropna).sum()
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "dropna, expected",
    [
        (True, pd.Series([210.0, 350.0], index=["a", "b"], name="Max Speed")),
        (
            False,
            pd.Series([210.0, 350.0, 20.0], index=["a", "b", np.nan], name="Max Speed"),
        ),
    ],
)
def test_groupby_dropna_series_by(dropna, expected):
    ser = pd.Series(
        [390.0, 350.0, 30.0, 20.0],
        index=["Falcon", "Falcon", "Parrot", "Parrot"],
        name="Max Speed",
    )

    result = ser.groupby(["a", "b", "a", np.nan], dropna=dropna).mean()
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("dropna", (False, True))
def test_grouper_dropna_propagation(dropna):
    # GH 36604
    df = pd.DataFrame({"A": [0, 0, 1, None], "B": [1, 2, 3, None]})
    gb = df.groupby("A", dropna=dropna)
    assert gb._grouper.dropna == dropna


@pytest.mark.parametrize(
    "index",
    [
        pd.RangeIndex(0, 4),
        list("abcd"),
        pd.MultiIndex.from_product([(1, 2), ("R", "B")], names=["num", "col"]),
    ],
)
def test_groupby_dataframe_slice_then_transform(dropna, index):
    # GH35014 & GH35612
    expected_data = {"B": [2, 2, 1, np.nan if dropna else 1]}

    df = pd.DataFrame({"A": [0, 0, 1, None], "B": [1, 2, 3, None]}, index=index)
    gb = df.groupby("A", dropna=dropna)

    result = gb.transform(len)
    expected = pd.DataFrame(expected_data, index=index)
    tm.assert_frame_equal(result, expected)

    result = gb[["B"]].transform(len)
    expected = pd.DataFrame(expected_data, index=index)
    tm.assert_frame_equal(result, expected)

    result = gb["B"].transform(len)
    expected = pd.Series(expected_data["B"], index=index, name="B")
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "dropna, tuples, outputs",
    [
        (
            True,
            [["A", "B"], ["B", "A"]],
            {"c": [13.0, 123.23], "d": [12.0, 123.0], "e": [1.0, 1.0]},
        ),
        (
            False,
            [["A", "B"], ["A", np.nan], ["B", "A"]],
            {
                "c": [13.0, 12.3, 123.23],
                "d": [12.0, 233.0, 123.0],
                "e": [1.0, 12.0, 1.0],
            },
        ),
    ],
)
def test_groupby_dropna_multi_index_dataframe_agg(dropna, tuples, outputs):
    # GH 3729
    df_list = [
        ["A", "B", 12, 12, 12],
        ["A", None, 12.3, 233.0, 12],
        ["B", "A", 123.23, 123, 1],
        ["A", "B", 1, 1, 1.0],
    ]
    df = pd.DataFrame(df_list, columns=["a", "b", "c", "d", "e"])
    agg_dict = {"c": "sum", "d": "max", "e": "min"}
    grouped = df.groupby(["a", "b"], dropna=dropna).agg(agg_dict)

    mi = pd.MultiIndex.from_tuples(tuples, names=list("ab"))

    # Since right now, by default MI will drop NA from levels when we create MI
    # via `from_*`, so we need to add NA for level manually afterwards.
    if not dropna:
        mi = mi.set_levels(["A", "B", np.nan], level="b")
    expected = pd.DataFrame(outputs, index=mi)

    tm.assert_frame_equal(grouped, expected)


@pytest.mark.arm_slow
@pytest.mark.parametrize(
    "datetime1, datetime2",
    [
        (pd.Timestamp("2020-01-01"), pd.Timestamp("2020-02-01")),
        (pd.Timedelta("-2 days"), pd.Timedelta("-1 days")),
        (pd.Period("2020-01-01"), pd.Period("2020-02-01")),
    ],
)
@pytest.mark.parametrize("dropna, values", [(True, [12, 3]), (False, [12, 3, 6])])
def test_groupby_dropna_datetime_like_data(
    dropna, values, datetime1, datetime2, unique_nulls_fixture, unique_nulls_fixture2
):
    # 3729
    df = pd.DataFrame(
        {
            "values": [1, 2, 3, 4, 5, 6],
            "dt": [
                datetime1,
                unique_nulls_fixture,
                datetime2,
                unique_nulls_fixture2,
                datetime1,
                datetime1,
            ],
        }
    )

    if dropna:
        indexes = [datetime1, datetime2]
    else:
        indexes = [datetime1, datetime2, np.nan]

    grouped = df.groupby("dt", dropna=dropna).agg({"values": "sum"})
    expected = pd.DataFrame({"values": values}, index=pd.Index(indexes, name="dt"))

    tm.assert_frame_equal(grouped, expected)


@pytest.mark.parametrize(
    "dropna, data, selected_data, levels",
    [
        pytest.param(
            False,
            {"groups": ["a", "a", "b", np.nan], "values": [10, 10, 20, 30]},
            {"values": [0, 1, 0, 0]},
            ["a", "b", np.nan],
            id="dropna_false_has_nan",
        ),
        pytest.param(
            True,
            {"groups": ["a", "a", "b", np.nan], "values": [10, 10, 20, 30]},
            {"values": [0, 1, 0]},
            None,
            id="dropna_true_has_nan",
        ),
        pytest.param(
            # no nan in "groups"; dropna=True|False should be same.
            False,
            {"groups": ["a", "a", "b", "c"], "values": [10, 10, 20, 30]},
            {"values": [0, 1, 0, 0]},
            None,
            id="dropna_false_no_nan",
        ),
        pytest.param(
            # no nan in "groups"; dropna=True|False should be same.
            True,
            {"groups": ["a", "a", "b", "c"], "values": [10, 10, 20, 30]},
            {"values": [0, 1, 0, 0]},
            None,
            id="dropna_true_no_nan",
        ),
    ],
)
def test_groupby_apply_with_dropna_for_multi_index(dropna, data, selected_data, levels):
    # GH 35889

    df = pd.DataFrame(data)
    gb = df.groupby("groups", dropna=dropna)
    msg = "DataFrameGroupBy.apply operated on the grouping columns"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = gb.apply(lambda grp: pd.DataFrame({"values": range(len(grp))}))

    mi_tuples = tuple(zip(data["groups"], selected_data["values"]))
    mi = pd.MultiIndex.from_tuples(mi_tuples, names=["groups", None])
    # Since right now, by default MI will drop NA from levels when we create MI
    # via `from_*`, so we need to add NA for level manually afterwards.
    if not dropna and levels:
        mi = mi.set_levels(levels, level="groups")

    expected = pd.DataFrame(selected_data, index=mi)
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("input_index", [None, ["a"], ["a", "b"]])
@pytest.mark.parametrize("keys", [["a"], ["a", "b"]])
@pytest.mark.parametrize("series", [True, False])
def test_groupby_dropna_with_multiindex_input(input_index, keys, series):
    # GH#46783
    obj = pd.DataFrame(
        {
            "a": [1, np.nan],
            "b": [1, 1],
            "c": [2, 3],
        }
    )

    expected = obj.set_index(keys)
    if series:
        expected = expected["c"]
    elif input_index == ["a", "b"] and keys == ["a"]:
        # Column b should not be aggregated
        expected = expected[["c"]]

    if input_index is not None:
        obj = obj.set_index(input_index)
    gb = obj.groupby(keys, dropna=False)
    if series:
        gb = gb["c"]
    result = gb.sum()

    tm.assert_equal(result, expected)


def test_groupby_nan_included():
    # GH 35646
    data = {"group": ["g1", np.nan, "g1", "g2", np.nan], "B": [0, 1, 2, 3, 4]}
    df = pd.DataFrame(data)
    grouped = df.groupby("group", dropna=False)
    result = grouped.indices
    dtype = np.intp
    expected = {
        "g1": np.array([0, 2], dtype=dtype),
        "g2": np.array([3], dtype=dtype),
        np.nan: np.array([1, 4], dtype=dtype),
    }
    for result_values, expected_values in zip(result.values(), expected.values()):
        tm.assert_numpy_array_equal(result_values, expected_values)
    assert np.isnan(list(result.keys())[2])
    assert list(result.keys())[0:2] == ["g1", "g2"]


def test_groupby_drop_nan_with_multi_index():
    # GH 39895
    df = pd.DataFrame([[np.nan, 0, 1]], columns=["a", "b", "c"])
    df = df.set_index(["a", "b"])
    result = df.groupby(["a", "b"], dropna=False).first()
    expected = df
    tm.assert_frame_equal(result, expected)


# sequence_index enumerates all strings made up of x, y, z of length 4
@pytest.mark.parametrize("sequence_index", range(3**4))
@pytest.mark.parametrize(
    "dtype",
    [
        None,
        "UInt8",
        "Int8",
        "UInt16",
        "Int16",
        "UInt32",
        "Int32",
        "UInt64",
        "Int64",
        "Float32",
        "Int64",
        "Float64",
        "category",
        "string",
        pytest.param(
            "string[pyarrow]",
            marks=pytest.mark.skipif(
                pa_version_under10p1, reason="pyarrow is not installed"
            ),
        ),
        "datetime64[ns]",
        "period[d]",
        "Sparse[float]",
    ],
)
@pytest.mark.parametrize("test_series", [True, False])
def test_no_sort_keep_na(sequence_index, dtype, test_series, as_index):
    # GH#46584, GH#48794

    # Convert sequence_index into a string sequence, e.g. 5 becomes "xxyz"
    # This sequence is used for the grouper.
    sequence = "".join(
        [{0: "x", 1: "y", 2: "z"}[sequence_index // (3**k) % 3] for k in range(4)]
    )

    # Unique values to use for grouper, depends on dtype
    if dtype in ("string", "string[pyarrow]"):
        uniques = {"x": "x", "y": "y", "z": pd.NA}
    elif dtype in ("datetime64[ns]", "period[d]"):
        uniques = {"x": "2016-01-01", "y": "2017-01-01", "z": pd.NA}
    else:
        uniques = {"x": 1, "y": 2, "z": np.nan}

    df = pd.DataFrame(
        {
            "key": pd.Series([uniques[label] for label in sequence], dtype=dtype),
            "a": [0, 1, 2, 3],
        }
    )
    gb = df.groupby("key", dropna=False, sort=False, as_index=as_index, observed=False)
    if test_series:
        gb = gb["a"]
    result = gb.sum()

    # Manually compute the groupby sum, use the labels "x", "y", and "z" to avoid
    # issues with hashing np.nan
    summed = {}
    for idx, label in enumerate(sequence):
        summed[label] = summed.get(label, 0) + idx
    if dtype == "category":
        index = pd.CategoricalIndex(
            [uniques[e] for e in summed],
            df["key"].cat.categories,
            name="key",
        )
    elif isinstance(dtype, str) and dtype.startswith("Sparse"):
        index = pd.Index(
            pd.array([uniques[label] for label in summed], dtype=dtype), name="key"
        )
    else:
        index = pd.Index([uniques[label] for label in summed], dtype=dtype, name="key")
    expected = pd.Series(summed.values(), index=index, name="a", dtype=None)
    if not test_series:
        expected = expected.to_frame()
    if not as_index:
        expected = expected.reset_index()
        if dtype is not None and dtype.startswith("Sparse"):
            expected["key"] = expected["key"].astype(dtype)

    tm.assert_equal(result, expected)


@pytest.mark.parametrize("test_series", [True, False])
@pytest.mark.parametrize("dtype", [object, None])
def test_null_is_null_for_dtype(
    sort, dtype, nulls_fixture, nulls_fixture2, test_series
):
    # GH#48506 - groups should always result in using the null for the dtype
    df = pd.DataFrame({"a": [1, 2]})
    groups = pd.Series([nulls_fixture, nulls_fixture2], dtype=dtype)
    obj = df["a"] if test_series else df
    gb = obj.groupby(groups, dropna=False, sort=sort)
    result = gb.sum()
    index = pd.Index([na_value_for_dtype(groups.dtype)])
    expected = pd.DataFrame({"a": [3]}, index=index)
    if test_series:
        tm.assert_series_equal(result, expected["a"])
    else:
        tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("index_kind", ["range", "single", "multi"])
def test_categorical_reducers(reduction_func, observed, sort, as_index, index_kind):
    # Ensure there is at least one null value by appending to the end
    values = np.append(np.random.default_rng(2).choice([1, 2, None], size=19), None)
    df = pd.DataFrame(
        {"x": pd.Categorical(values, categories=[1, 2, 3]), "y": range(20)}
    )

    # Strategy: Compare to dropna=True by filling null values with a new code
    df_filled = df.copy()
    df_filled["x"] = pd.Categorical(values, categories=[1, 2, 3, 4]).fillna(4)

    if index_kind == "range":
        keys = ["x"]
    elif index_kind == "single":
        keys = ["x"]
        df = df.set_index("x")
        df_filled = df_filled.set_index("x")
    else:
        keys = ["x", "x2"]
        df["x2"] = df["x"]
        df = df.set_index(["x", "x2"])
        df_filled["x2"] = df_filled["x"]
        df_filled = df_filled.set_index(["x", "x2"])
    args = get_groupby_method_args(reduction_func, df)
    args_filled = get_groupby_method_args(reduction_func, df_filled)
    if reduction_func == "corrwith" and index_kind == "range":
        # Don't include the grouping columns so we can call reset_index
        args = (args[0].drop(columns=keys),)
        args_filled = (args_filled[0].drop(columns=keys),)

    gb_keepna = df.groupby(
        keys, dropna=False, observed=observed, sort=sort, as_index=as_index
    )

    if not observed and reduction_func in ["idxmin", "idxmax"]:
        with pytest.raises(
            ValueError, match="empty group due to unobserved categories"
        ):
            getattr(gb_keepna, reduction_func)(*args)
        return

    gb_filled = df_filled.groupby(keys, observed=observed, sort=sort, as_index=True)
    expected = getattr(gb_filled, reduction_func)(*args_filled).reset_index()
    expected["x"] = expected["x"].cat.remove_categories([4])
    if index_kind == "multi":
        expected["x2"] = expected["x2"].cat.remove_categories([4])
    if as_index:
        if index_kind == "multi":
            expected = expected.set_index(["x", "x2"])
        else:
            expected = expected.set_index("x")
    elif index_kind != "range" and reduction_func != "size":
        # size, unlike other methods, has the desired behavior in GH#49519
        expected = expected.drop(columns="x")
        if index_kind == "multi":
            expected = expected.drop(columns="x2")
    if reduction_func in ("idxmax", "idxmin") and index_kind != "range":
        # expected was computed with a RangeIndex; need to translate to index values
        values = expected["y"].values.tolist()
        if index_kind == "single":
            values = [np.nan if e == 4 else e for e in values]
            expected["y"] = pd.Categorical(values, categories=[1, 2, 3])
        else:
            values = [(np.nan, np.nan) if e == (4, 4) else e for e in values]
            expected["y"] = values
    if reduction_func == "size":
        # size, unlike other methods, has the desired behavior in GH#49519
        expected = expected.rename(columns={0: "size"})
        if as_index:
            expected = expected["size"].rename(None)

    if as_index or index_kind == "range" or reduction_func == "size":
        warn = None
    else:
        warn = FutureWarning
    msg = "A grouping .* was excluded from the result"
    with tm.assert_produces_warning(warn, match=msg):
        result = getattr(gb_keepna, reduction_func)(*args)

    # size will return a Series, others are DataFrame
    tm.assert_equal(result, expected)


def test_categorical_transformers(
    request, transformation_func, observed, sort, as_index
):
    # GH#36327
    if transformation_func == "fillna":
        msg = "GH#49651 fillna may incorrectly reorders results when dropna=False"
        request.applymarker(pytest.mark.xfail(reason=msg, strict=False))

    values = np.append(np.random.default_rng(2).choice([1, 2, None], size=19), None)
    df = pd.DataFrame(
        {"x": pd.Categorical(values, categories=[1, 2, 3]), "y": range(20)}
    )
    args = get_groupby_method_args(transformation_func, df)

    # Compute result for null group
    null_group_values = df[df["x"].isnull()]["y"]
    if transformation_func == "cumcount":
        null_group_data = list(range(len(null_group_values)))
    elif transformation_func == "ngroup":
        if sort:
            if observed:
                na_group = df["x"].nunique(dropna=False) - 1
            else:
                # TODO: Should this be 3?
                na_group = df["x"].nunique(dropna=False) - 1
        else:
            na_group = df.iloc[: null_group_values.index[0]]["x"].nunique()
        null_group_data = len(null_group_values) * [na_group]
    else:
        null_group_data = getattr(null_group_values, transformation_func)(*args)
    null_group_result = pd.DataFrame({"y": null_group_data})

    gb_keepna = df.groupby(
        "x", dropna=False, observed=observed, sort=sort, as_index=as_index
    )
    gb_dropna = df.groupby("x", dropna=True, observed=observed, sort=sort)

    msg = "The default fill_method='ffill' in DataFrameGroupBy.pct_change is deprecated"
    if transformation_func == "pct_change":
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = getattr(gb_keepna, "pct_change")(*args)
    else:
        result = getattr(gb_keepna, transformation_func)(*args)
    expected = getattr(gb_dropna, transformation_func)(*args)

    for iloc, value in zip(
        df[df["x"].isnull()].index.tolist(), null_group_result.values.ravel()
    ):
        if expected.ndim == 1:
            expected.iloc[iloc] = value
        else:
            expected.iloc[iloc, 0] = value
    if transformation_func == "ngroup":
        expected[df["x"].notnull() & expected.ge(na_group)] += 1
    if transformation_func not in ("rank", "diff", "pct_change", "shift"):
        expected = expected.astype("int64")

    tm.assert_equal(result, expected)


@pytest.mark.parametrize("method", ["head", "tail"])
def test_categorical_head_tail(method, observed, sort, as_index):
    # GH#36327
    values = np.random.default_rng(2).choice([1, 2, None], 30)
    df = pd.DataFrame(
        {"x": pd.Categorical(values, categories=[1, 2, 3]), "y": range(len(values))}
    )
    gb = df.groupby("x", dropna=False, observed=observed, sort=sort, as_index=as_index)
    result = getattr(gb, method)()

    if method == "tail":
        values = values[::-1]
    # Take the top 5 values from each group
    mask = (
        ((values == 1) & ((values == 1).cumsum() <= 5))
        | ((values == 2) & ((values == 2).cumsum() <= 5))
        # flake8 doesn't like the vectorized check for None, thinks we should use `is`
        | ((values == None) & ((values == None).cumsum() <= 5))  # noqa: E711
    )
    if method == "tail":
        mask = mask[::-1]
    expected = df[mask]

    tm.assert_frame_equal(result, expected)


def test_categorical_agg():
    # GH#36327
    values = np.random.default_rng(2).choice([1, 2, None], 30)
    df = pd.DataFrame(
        {"x": pd.Categorical(values, categories=[1, 2, 3]), "y": range(len(values))}
    )
    gb = df.groupby("x", dropna=False, observed=False)
    result = gb.agg(lambda x: x.sum())
    expected = gb.sum()
    tm.assert_frame_equal(result, expected)


def test_categorical_transform():
    # GH#36327
    values = np.random.default_rng(2).choice([1, 2, None], 30)
    df = pd.DataFrame(
        {"x": pd.Categorical(values, categories=[1, 2, 3]), "y": range(len(values))}
    )
    gb = df.groupby("x", dropna=False, observed=False)
    result = gb.transform(lambda x: x.sum())
    expected = gb.transform("sum")
    tm.assert_frame_equal(result, expected)
