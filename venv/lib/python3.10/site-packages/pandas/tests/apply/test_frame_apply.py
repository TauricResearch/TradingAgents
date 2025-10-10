from datetime import datetime
import warnings

import numpy as np
import pytest

from pandas.compat import is_platform_arm

from pandas.core.dtypes.dtypes import CategoricalDtype

import pandas as pd
from pandas import (
    DataFrame,
    MultiIndex,
    Series,
    Timestamp,
    date_range,
)
import pandas._testing as tm
from pandas.tests.frame.common import zip_frames
from pandas.util.version import Version


@pytest.fixture
def int_frame_const_col():
    """
    Fixture for DataFrame of ints which are constant per column

    Columns are ['A', 'B', 'C'], with values (per column): [1, 2, 3]
    """
    df = DataFrame(
        np.tile(np.arange(3, dtype="int64"), 6).reshape(6, -1) + 1,
        columns=["A", "B", "C"],
    )
    return df


@pytest.fixture(params=["python", pytest.param("numba", marks=pytest.mark.single_cpu)])
def engine(request):
    if request.param == "numba":
        pytest.importorskip("numba")
    return request.param


def test_apply(float_frame, engine, request):
    if engine == "numba":
        mark = pytest.mark.xfail(reason="numba engine not supporting numpy ufunc yet")
        request.node.add_marker(mark)
    with np.errstate(all="ignore"):
        # ufunc
        result = np.sqrt(float_frame["A"])
        expected = float_frame.apply(np.sqrt, engine=engine)["A"]
        tm.assert_series_equal(result, expected)

        # aggregator
        result = float_frame.apply(np.mean, engine=engine)["A"]
        expected = np.mean(float_frame["A"])
        assert result == expected

        d = float_frame.index[0]
        result = float_frame.apply(np.mean, axis=1, engine=engine)
        expected = np.mean(float_frame.xs(d))
        assert result[d] == expected
        assert result.index is float_frame.index


@pytest.mark.parametrize("axis", [0, 1])
@pytest.mark.parametrize("raw", [True, False])
def test_apply_args(float_frame, axis, raw, engine, request):
    if engine == "numba":
        numba = pytest.importorskip("numba")
        if Version(numba.__version__) == Version("0.61") and is_platform_arm():
            pytest.skip(f"Segfaults on ARM platforms with numba {numba.__version__}")
        mark = pytest.mark.xfail(reason="numba engine doesn't support args")
        request.node.add_marker(mark)
    result = float_frame.apply(
        lambda x, y: x + y, axis, args=(1,), raw=raw, engine=engine
    )
    expected = float_frame + 1
    tm.assert_frame_equal(result, expected)


def test_apply_categorical_func():
    # GH 9573
    df = DataFrame({"c0": ["A", "A", "B", "B"], "c1": ["C", "C", "D", "D"]})
    result = df.apply(lambda ts: ts.astype("category"))

    assert result.shape == (4, 2)
    assert isinstance(result["c0"].dtype, CategoricalDtype)
    assert isinstance(result["c1"].dtype, CategoricalDtype)


def test_apply_axis1_with_ea():
    # GH#36785
    expected = DataFrame({"A": [Timestamp("2013-01-01", tz="UTC")]})
    result = expected.apply(lambda x: x, axis=1)
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "data, dtype",
    [(1, None), (1, CategoricalDtype([1])), (Timestamp("2013-01-01", tz="UTC"), None)],
)
def test_agg_axis1_duplicate_index(data, dtype):
    # GH 42380
    expected = DataFrame([[data], [data]], index=["a", "a"], dtype=dtype)
    result = expected.agg(lambda x: x, axis=1)
    tm.assert_frame_equal(result, expected)


def test_apply_mixed_datetimelike():
    # mixed datetimelike
    # GH 7778
    expected = DataFrame(
        {
            "A": date_range("20130101", periods=3),
            "B": pd.to_timedelta(np.arange(3), unit="s"),
        }
    )
    result = expected.apply(lambda x: x, axis=1)
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("func", [np.sqrt, np.mean])
def test_apply_empty(func, engine):
    # empty
    empty_frame = DataFrame()

    result = empty_frame.apply(func, engine=engine)
    assert result.empty


def test_apply_float_frame(float_frame, engine):
    no_rows = float_frame[:0]
    result = no_rows.apply(lambda x: x.mean(), engine=engine)
    expected = Series(np.nan, index=float_frame.columns)
    tm.assert_series_equal(result, expected)

    no_cols = float_frame.loc[:, []]
    result = no_cols.apply(lambda x: x.mean(), axis=1, engine=engine)
    expected = Series(np.nan, index=float_frame.index)
    tm.assert_series_equal(result, expected)


def test_apply_empty_except_index(engine):
    # GH 2476
    expected = DataFrame(index=["a"])
    result = expected.apply(lambda x: x["a"], axis=1, engine=engine)
    tm.assert_frame_equal(result, expected)


def test_apply_with_reduce_empty():
    # reduce with an empty DataFrame
    empty_frame = DataFrame()

    x = []
    result = empty_frame.apply(x.append, axis=1, result_type="expand")
    tm.assert_frame_equal(result, empty_frame)
    result = empty_frame.apply(x.append, axis=1, result_type="reduce")
    expected = Series([], dtype=np.float64)
    tm.assert_series_equal(result, expected)

    empty_with_cols = DataFrame(columns=["a", "b", "c"])
    result = empty_with_cols.apply(x.append, axis=1, result_type="expand")
    tm.assert_frame_equal(result, empty_with_cols)
    result = empty_with_cols.apply(x.append, axis=1, result_type="reduce")
    expected = Series([], dtype=np.float64)
    tm.assert_series_equal(result, expected)

    # Ensure that x.append hasn't been called
    assert x == []


@pytest.mark.parametrize("func", ["sum", "prod", "any", "all"])
def test_apply_funcs_over_empty(func):
    # GH 28213
    df = DataFrame(columns=["a", "b", "c"])

    result = df.apply(getattr(np, func))
    expected = getattr(df, func)()
    if func in ("sum", "prod"):
        expected = expected.astype(float)
    tm.assert_series_equal(result, expected)


def test_nunique_empty():
    # GH 28213
    df = DataFrame(columns=["a", "b", "c"])

    result = df.nunique()
    expected = Series(0, index=df.columns)
    tm.assert_series_equal(result, expected)

    result = df.T.nunique()
    expected = Series([], dtype=np.float64)
    tm.assert_series_equal(result, expected)


def test_apply_standard_nonunique():
    df = DataFrame([[1, 2, 3], [4, 5, 6], [7, 8, 9]], index=["a", "a", "c"])

    result = df.apply(lambda s: s[0], axis=1)
    expected = Series([1, 4, 7], ["a", "a", "c"])
    tm.assert_series_equal(result, expected)

    result = df.T.apply(lambda s: s[0], axis=0)
    tm.assert_series_equal(result, expected)


def test_apply_broadcast_scalars(float_frame):
    # scalars
    result = float_frame.apply(np.mean, result_type="broadcast")
    expected = DataFrame([float_frame.mean()], index=float_frame.index)
    tm.assert_frame_equal(result, expected)


def test_apply_broadcast_scalars_axis1(float_frame):
    result = float_frame.apply(np.mean, axis=1, result_type="broadcast")
    m = float_frame.mean(axis=1)
    expected = DataFrame({c: m for c in float_frame.columns})
    tm.assert_frame_equal(result, expected)


def test_apply_broadcast_lists_columns(float_frame):
    # lists
    result = float_frame.apply(
        lambda x: list(range(len(float_frame.columns))),
        axis=1,
        result_type="broadcast",
    )
    m = list(range(len(float_frame.columns)))
    expected = DataFrame(
        [m] * len(float_frame.index),
        dtype="float64",
        index=float_frame.index,
        columns=float_frame.columns,
    )
    tm.assert_frame_equal(result, expected)


def test_apply_broadcast_lists_index(float_frame):
    result = float_frame.apply(
        lambda x: list(range(len(float_frame.index))), result_type="broadcast"
    )
    m = list(range(len(float_frame.index)))
    expected = DataFrame(
        {c: m for c in float_frame.columns},
        dtype="float64",
        index=float_frame.index,
    )
    tm.assert_frame_equal(result, expected)


def test_apply_broadcast_list_lambda_func(int_frame_const_col):
    # preserve columns
    df = int_frame_const_col
    result = df.apply(lambda x: [1, 2, 3], axis=1, result_type="broadcast")
    tm.assert_frame_equal(result, df)


def test_apply_broadcast_series_lambda_func(int_frame_const_col):
    df = int_frame_const_col
    result = df.apply(
        lambda x: Series([1, 2, 3], index=list("abc")),
        axis=1,
        result_type="broadcast",
    )
    expected = df.copy()
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("axis", [0, 1])
def test_apply_raw_float_frame(float_frame, axis, engine):
    if engine == "numba":
        pytest.skip("numba can't handle when UDF returns None.")

    def _assert_raw(x):
        assert isinstance(x, np.ndarray)
        assert x.ndim == 1

    float_frame.apply(_assert_raw, axis=axis, engine=engine, raw=True)


@pytest.mark.parametrize("axis", [0, 1])
def test_apply_raw_float_frame_lambda(float_frame, axis, engine):
    result = float_frame.apply(np.mean, axis=axis, engine=engine, raw=True)
    expected = float_frame.apply(lambda x: x.values.mean(), axis=axis)
    tm.assert_series_equal(result, expected)


def test_apply_raw_float_frame_no_reduction(float_frame, engine):
    # no reduction
    result = float_frame.apply(lambda x: x * 2, engine=engine, raw=True)
    expected = float_frame * 2
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("axis", [0, 1])
def test_apply_raw_mixed_type_frame(axis, engine):
    if engine == "numba":
        pytest.skip("isinstance check doesn't work with numba")

    def _assert_raw(x):
        assert isinstance(x, np.ndarray)
        assert x.ndim == 1

    # Mixed dtype (GH-32423)
    df = DataFrame(
        {
            "a": 1.0,
            "b": 2,
            "c": "foo",
            "float32": np.array([1.0] * 10, dtype="float32"),
            "int32": np.array([1] * 10, dtype="int32"),
        },
        index=np.arange(10),
    )
    df.apply(_assert_raw, axis=axis, engine=engine, raw=True)


def test_apply_axis1(float_frame):
    d = float_frame.index[0]
    result = float_frame.apply(np.mean, axis=1)[d]
    expected = np.mean(float_frame.xs(d))
    assert result == expected


def test_apply_mixed_dtype_corner():
    df = DataFrame({"A": ["foo"], "B": [1.0]})
    result = df[:0].apply(np.mean, axis=1)
    # the result here is actually kind of ambiguous, should it be a Series
    # or a DataFrame?
    expected = Series(np.nan, index=pd.Index([], dtype="int64"))
    tm.assert_series_equal(result, expected)


def test_apply_mixed_dtype_corner_indexing():
    df = DataFrame({"A": ["foo"], "B": [1.0]})
    result = df.apply(lambda x: x["A"], axis=1)
    expected = Series(["foo"], index=[0])
    tm.assert_series_equal(result, expected)

    result = df.apply(lambda x: x["B"], axis=1)
    expected = Series([1.0], index=[0])
    tm.assert_series_equal(result, expected)


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
@pytest.mark.parametrize("ax", ["index", "columns"])
@pytest.mark.parametrize(
    "func", [lambda x: x, lambda x: x.mean()], ids=["identity", "mean"]
)
@pytest.mark.parametrize("raw", [True, False])
@pytest.mark.parametrize("axis", [0, 1])
def test_apply_empty_infer_type(ax, func, raw, axis, engine, request):
    df = DataFrame(**{ax: ["a", "b", "c"]})

    with np.errstate(all="ignore"):
        test_res = func(np.array([], dtype="f8"))
        is_reduction = not isinstance(test_res, np.ndarray)

        result = df.apply(func, axis=axis, engine=engine, raw=raw)
        if is_reduction:
            agg_axis = df._get_agg_axis(axis)
            assert isinstance(result, Series)
            assert result.index is agg_axis
        else:
            assert isinstance(result, DataFrame)


def test_apply_empty_infer_type_broadcast():
    no_cols = DataFrame(index=["a", "b", "c"])
    result = no_cols.apply(lambda x: x.mean(), result_type="broadcast")
    assert isinstance(result, DataFrame)


def test_apply_with_args_kwds_add_some(float_frame):
    def add_some(x, howmuch=0):
        return x + howmuch

    result = float_frame.apply(add_some, howmuch=2)
    expected = float_frame.apply(lambda x: x + 2)
    tm.assert_frame_equal(result, expected)


def test_apply_with_args_kwds_agg_and_add(float_frame):
    def agg_and_add(x, howmuch=0):
        return x.mean() + howmuch

    result = float_frame.apply(agg_and_add, howmuch=2)
    expected = float_frame.apply(lambda x: x.mean() + 2)
    tm.assert_series_equal(result, expected)


def test_apply_with_args_kwds_subtract_and_divide(float_frame):
    def subtract_and_divide(x, sub, divide=1):
        return (x - sub) / divide

    result = float_frame.apply(subtract_and_divide, args=(2,), divide=2)
    expected = float_frame.apply(lambda x: (x - 2.0) / 2.0)
    tm.assert_frame_equal(result, expected)


def test_apply_yield_list(float_frame):
    result = float_frame.apply(list)
    tm.assert_frame_equal(result, float_frame)


def test_apply_reduce_Series(float_frame):
    float_frame.iloc[::2, float_frame.columns.get_loc("A")] = np.nan
    expected = float_frame.mean(1)
    result = float_frame.apply(np.mean, axis=1)
    tm.assert_series_equal(result, expected)


def test_apply_reduce_to_dict():
    # GH 25196 37544
    data = DataFrame([[1, 2], [3, 4]], columns=["c0", "c1"], index=["i0", "i1"])

    result = data.apply(dict, axis=0)
    expected = Series([{"i0": 1, "i1": 3}, {"i0": 2, "i1": 4}], index=data.columns)
    tm.assert_series_equal(result, expected)

    result = data.apply(dict, axis=1)
    expected = Series([{"c0": 1, "c1": 2}, {"c0": 3, "c1": 4}], index=data.index)
    tm.assert_series_equal(result, expected)


def test_apply_differently_indexed():
    df = DataFrame(np.random.default_rng(2).standard_normal((20, 10)))

    result = df.apply(Series.describe, axis=0)
    expected = DataFrame({i: v.describe() for i, v in df.items()}, columns=df.columns)
    tm.assert_frame_equal(result, expected)

    result = df.apply(Series.describe, axis=1)
    expected = DataFrame({i: v.describe() for i, v in df.T.items()}, columns=df.index).T
    tm.assert_frame_equal(result, expected)


def test_apply_bug():
    # GH 6125
    positions = DataFrame(
        [
            [1, "ABC0", 50],
            [1, "YUM0", 20],
            [1, "DEF0", 20],
            [2, "ABC1", 50],
            [2, "YUM1", 20],
            [2, "DEF1", 20],
        ],
        columns=["a", "market", "position"],
    )

    def f(r):
        return r["market"]

    expected = positions.apply(f, axis=1)

    positions = DataFrame(
        [
            [datetime(2013, 1, 1), "ABC0", 50],
            [datetime(2013, 1, 2), "YUM0", 20],
            [datetime(2013, 1, 3), "DEF0", 20],
            [datetime(2013, 1, 4), "ABC1", 50],
            [datetime(2013, 1, 5), "YUM1", 20],
            [datetime(2013, 1, 6), "DEF1", 20],
        ],
        columns=["a", "market", "position"],
    )
    result = positions.apply(f, axis=1)
    tm.assert_series_equal(result, expected)


def test_apply_convert_objects():
    expected = DataFrame(
        {
            "A": [
                "foo",
                "foo",
                "foo",
                "foo",
                "bar",
                "bar",
                "bar",
                "bar",
                "foo",
                "foo",
                "foo",
            ],
            "B": [
                "one",
                "one",
                "one",
                "two",
                "one",
                "one",
                "one",
                "two",
                "two",
                "two",
                "one",
            ],
            "C": [
                "dull",
                "dull",
                "shiny",
                "dull",
                "dull",
                "shiny",
                "shiny",
                "dull",
                "shiny",
                "shiny",
                "shiny",
            ],
            "D": np.random.default_rng(2).standard_normal(11),
            "E": np.random.default_rng(2).standard_normal(11),
            "F": np.random.default_rng(2).standard_normal(11),
        }
    )

    result = expected.apply(lambda x: x, axis=1)
    tm.assert_frame_equal(result, expected)


def test_apply_attach_name(float_frame):
    result = float_frame.apply(lambda x: x.name)
    expected = Series(float_frame.columns, index=float_frame.columns)
    tm.assert_series_equal(result, expected)


def test_apply_attach_name_axis1(float_frame):
    result = float_frame.apply(lambda x: x.name, axis=1)
    expected = Series(float_frame.index, index=float_frame.index)
    tm.assert_series_equal(result, expected)


def test_apply_attach_name_non_reduction(float_frame):
    # non-reductions
    result = float_frame.apply(lambda x: np.repeat(x.name, len(x)))
    expected = DataFrame(
        np.tile(float_frame.columns, (len(float_frame.index), 1)),
        index=float_frame.index,
        columns=float_frame.columns,
    )
    tm.assert_frame_equal(result, expected)


def test_apply_attach_name_non_reduction_axis1(float_frame):
    result = float_frame.apply(lambda x: np.repeat(x.name, len(x)), axis=1)
    expected = Series(
        np.repeat(t[0], len(float_frame.columns)) for t in float_frame.itertuples()
    )
    expected.index = float_frame.index
    tm.assert_series_equal(result, expected)


def test_apply_multi_index():
    index = MultiIndex.from_arrays([["a", "a", "b"], ["c", "d", "d"]])
    s = DataFrame([[1, 2], [3, 4], [5, 6]], index=index, columns=["col1", "col2"])
    result = s.apply(lambda x: Series({"min": min(x), "max": max(x)}), 1)
    expected = DataFrame([[1, 2], [3, 4], [5, 6]], index=index, columns=["min", "max"])
    tm.assert_frame_equal(result, expected, check_like=True)


@pytest.mark.parametrize(
    "df, dicts",
    [
        [
            DataFrame([["foo", "bar"], ["spam", "eggs"]]),
            Series([{0: "foo", 1: "spam"}, {0: "bar", 1: "eggs"}]),
        ],
        [DataFrame([[0, 1], [2, 3]]), Series([{0: 0, 1: 2}, {0: 1, 1: 3}])],
    ],
)
def test_apply_dict(df, dicts):
    # GH 8735
    fn = lambda x: x.to_dict()
    reduce_true = df.apply(fn, result_type="reduce")
    reduce_false = df.apply(fn, result_type="expand")
    reduce_none = df.apply(fn)

    tm.assert_series_equal(reduce_true, dicts)
    tm.assert_frame_equal(reduce_false, df)
    tm.assert_series_equal(reduce_none, dicts)


def test_apply_non_numpy_dtype():
    # GH 12244
    df = DataFrame({"dt": date_range("2015-01-01", periods=3, tz="Europe/Brussels")})
    result = df.apply(lambda x: x)
    tm.assert_frame_equal(result, df)

    result = df.apply(lambda x: x + pd.Timedelta("1day"))
    expected = DataFrame(
        {"dt": date_range("2015-01-02", periods=3, tz="Europe/Brussels")}
    )
    tm.assert_frame_equal(result, expected)


def test_apply_non_numpy_dtype_category():
    df = DataFrame({"dt": ["a", "b", "c", "a"]}, dtype="category")
    result = df.apply(lambda x: x)
    tm.assert_frame_equal(result, df)


def test_apply_dup_names_multi_agg():
    # GH 21063
    df = DataFrame([[0, 1], [2, 3]], columns=["a", "a"])
    expected = DataFrame([[0, 1]], columns=["a", "a"], index=["min"])
    result = df.agg(["min"])

    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("op", ["apply", "agg"])
def test_apply_nested_result_axis_1(op):
    # GH 13820
    def apply_list(row):
        return [2 * row["A"], 2 * row["C"], 2 * row["B"]]

    df = DataFrame(np.zeros((4, 4)), columns=list("ABCD"))
    result = getattr(df, op)(apply_list, axis=1)
    expected = Series(
        [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
    )
    tm.assert_series_equal(result, expected)


def test_apply_noreduction_tzaware_object():
    # https://github.com/pandas-dev/pandas/issues/31505
    expected = DataFrame(
        {"foo": [Timestamp("2020", tz="UTC")]}, dtype="datetime64[ns, UTC]"
    )
    result = expected.apply(lambda x: x)
    tm.assert_frame_equal(result, expected)
    result = expected.apply(lambda x: x.copy())
    tm.assert_frame_equal(result, expected)


def test_apply_function_runs_once():
    # https://github.com/pandas-dev/pandas/issues/30815

    df = DataFrame({"a": [1, 2, 3]})
    names = []  # Save row names function is applied to

    def reducing_function(row):
        names.append(row.name)

    def non_reducing_function(row):
        names.append(row.name)
        return row

    for func in [reducing_function, non_reducing_function]:
        del names[:]

        df.apply(func, axis=1)
        assert names == list(df.index)


def test_apply_raw_function_runs_once(engine):
    # https://github.com/pandas-dev/pandas/issues/34506
    if engine == "numba":
        pytest.skip("appending to list outside of numba func is not supported")

    df = DataFrame({"a": [1, 2, 3]})
    values = []  # Save row values function is applied to

    def reducing_function(row):
        values.extend(row)

    def non_reducing_function(row):
        values.extend(row)
        return row

    for func in [reducing_function, non_reducing_function]:
        del values[:]

        df.apply(func, engine=engine, raw=True, axis=1)
        assert values == list(df.a.to_list())


def test_apply_with_byte_string():
    # GH 34529
    df = DataFrame(np.array([b"abcd", b"efgh"]), columns=["col"])
    expected = DataFrame(np.array([b"abcd", b"efgh"]), columns=["col"], dtype=object)
    # After we make the apply we expect a dataframe just
    # like the original but with the object datatype
    result = df.apply(lambda x: x.astype("object"))
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("val", ["asd", 12, None, np.nan])
def test_apply_category_equalness(val):
    # Check if categorical comparisons on apply, GH 21239
    df_values = ["asd", None, 12, "asd", "cde", np.nan]
    df = DataFrame({"a": df_values}, dtype="category")

    result = df.a.apply(lambda x: x == val)
    expected = Series(
        [np.nan if pd.isnull(x) else x == val for x in df_values], name="a"
    )
    tm.assert_series_equal(result, expected)


# the user has supplied an opaque UDF where
# they are transforming the input that requires
# us to infer the output


def test_infer_row_shape():
    # GH 17437
    # if row shape is changing, infer it
    df = DataFrame(np.random.default_rng(2).random((10, 2)))
    result = df.apply(np.fft.fft, axis=0).shape
    assert result == (10, 2)

    result = df.apply(np.fft.rfft, axis=0).shape
    assert result == (6, 2)


@pytest.mark.parametrize(
    "ops, by_row, expected",
    [
        ({"a": lambda x: x + 1}, "compat", DataFrame({"a": [2, 3]})),
        ({"a": lambda x: x + 1}, False, DataFrame({"a": [2, 3]})),
        ({"a": lambda x: x.sum()}, "compat", Series({"a": 3})),
        ({"a": lambda x: x.sum()}, False, Series({"a": 3})),
        (
            {"a": ["sum", np.sum, lambda x: x.sum()]},
            "compat",
            DataFrame({"a": [3, 3, 3]}, index=["sum", "sum", "<lambda>"]),
        ),
        (
            {"a": ["sum", np.sum, lambda x: x.sum()]},
            False,
            DataFrame({"a": [3, 3, 3]}, index=["sum", "sum", "<lambda>"]),
        ),
        ({"a": lambda x: 1}, "compat", DataFrame({"a": [1, 1]})),
        ({"a": lambda x: 1}, False, Series({"a": 1})),
    ],
)
def test_dictlike_lambda(ops, by_row, expected):
    # GH53601
    df = DataFrame({"a": [1, 2]})
    result = df.apply(ops, by_row=by_row)
    tm.assert_equal(result, expected)


@pytest.mark.parametrize(
    "ops",
    [
        {"a": lambda x: x + 1},
        {"a": lambda x: x.sum()},
        {"a": ["sum", np.sum, lambda x: x.sum()]},
        {"a": lambda x: 1},
    ],
)
def test_dictlike_lambda_raises(ops):
    # GH53601
    df = DataFrame({"a": [1, 2]})
    with pytest.raises(ValueError, match="by_row=True not allowed"):
        df.apply(ops, by_row=True)


def test_with_dictlike_columns():
    # GH 17602
    df = DataFrame([[1, 2], [1, 2]], columns=["a", "b"])
    result = df.apply(lambda x: {"s": x["a"] + x["b"]}, axis=1)
    expected = Series([{"s": 3} for t in df.itertuples()])
    tm.assert_series_equal(result, expected)

    df["tm"] = [
        Timestamp("2017-05-01 00:00:00"),
        Timestamp("2017-05-02 00:00:00"),
    ]
    result = df.apply(lambda x: {"s": x["a"] + x["b"]}, axis=1)
    tm.assert_series_equal(result, expected)

    # compose a series
    result = (df["a"] + df["b"]).apply(lambda x: {"s": x})
    expected = Series([{"s": 3}, {"s": 3}])
    tm.assert_series_equal(result, expected)


def test_with_dictlike_columns_with_datetime():
    # GH 18775
    df = DataFrame()
    df["author"] = ["X", "Y", "Z"]
    df["publisher"] = ["BBC", "NBC", "N24"]
    df["date"] = pd.to_datetime(
        ["17-10-2010 07:15:30", "13-05-2011 08:20:35", "15-01-2013 09:09:09"],
        dayfirst=True,
    )
    result = df.apply(lambda x: {}, axis=1)
    expected = Series([{}, {}, {}])
    tm.assert_series_equal(result, expected)


def test_with_dictlike_columns_with_infer():
    # GH 17602
    df = DataFrame([[1, 2], [1, 2]], columns=["a", "b"])
    result = df.apply(lambda x: {"s": x["a"] + x["b"]}, axis=1, result_type="expand")
    expected = DataFrame({"s": [3, 3]})
    tm.assert_frame_equal(result, expected)

    df["tm"] = [
        Timestamp("2017-05-01 00:00:00"),
        Timestamp("2017-05-02 00:00:00"),
    ]
    result = df.apply(lambda x: {"s": x["a"] + x["b"]}, axis=1, result_type="expand")
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "ops, by_row, expected",
    [
        ([lambda x: x + 1], "compat", DataFrame({("a", "<lambda>"): [2, 3]})),
        ([lambda x: x + 1], False, DataFrame({("a", "<lambda>"): [2, 3]})),
        ([lambda x: x.sum()], "compat", DataFrame({"a": [3]}, index=["<lambda>"])),
        ([lambda x: x.sum()], False, DataFrame({"a": [3]}, index=["<lambda>"])),
        (
            ["sum", np.sum, lambda x: x.sum()],
            "compat",
            DataFrame({"a": [3, 3, 3]}, index=["sum", "sum", "<lambda>"]),
        ),
        (
            ["sum", np.sum, lambda x: x.sum()],
            False,
            DataFrame({"a": [3, 3, 3]}, index=["sum", "sum", "<lambda>"]),
        ),
        (
            [lambda x: x + 1, lambda x: 3],
            "compat",
            DataFrame([[2, 3], [3, 3]], columns=[["a", "a"], ["<lambda>", "<lambda>"]]),
        ),
        (
            [lambda x: 2, lambda x: 3],
            False,
            DataFrame({"a": [2, 3]}, ["<lambda>", "<lambda>"]),
        ),
    ],
)
def test_listlike_lambda(ops, by_row, expected):
    # GH53601
    df = DataFrame({"a": [1, 2]})
    result = df.apply(ops, by_row=by_row)
    tm.assert_equal(result, expected)


@pytest.mark.parametrize(
    "ops",
    [
        [lambda x: x + 1],
        [lambda x: x.sum()],
        ["sum", np.sum, lambda x: x.sum()],
        [lambda x: x + 1, lambda x: 3],
    ],
)
def test_listlike_lambda_raises(ops):
    # GH53601
    df = DataFrame({"a": [1, 2]})
    with pytest.raises(ValueError, match="by_row=True not allowed"):
        df.apply(ops, by_row=True)


def test_with_listlike_columns():
    # GH 17348
    df = DataFrame(
        {
            "a": Series(np.random.default_rng(2).standard_normal(4)),
            "b": ["a", "list", "of", "words"],
            "ts": date_range("2016-10-01", periods=4, freq="h"),
        }
    )

    result = df[["a", "b"]].apply(tuple, axis=1)
    expected = Series([t[1:] for t in df[["a", "b"]].itertuples()])
    tm.assert_series_equal(result, expected)

    result = df[["a", "ts"]].apply(tuple, axis=1)
    expected = Series([t[1:] for t in df[["a", "ts"]].itertuples()])
    tm.assert_series_equal(result, expected)


def test_with_listlike_columns_returning_list():
    # GH 18919
    df = DataFrame({"x": Series([["a", "b"], ["q"]]), "y": Series([["z"], ["q", "t"]])})
    df.index = MultiIndex.from_tuples([("i0", "j0"), ("i1", "j1")])

    result = df.apply(lambda row: [el for el in row["x"] if el in row["y"]], axis=1)
    expected = Series([[], ["q"]], index=df.index)
    tm.assert_series_equal(result, expected)


def test_infer_output_shape_columns():
    # GH 18573

    df = DataFrame(
        {
            "number": [1.0, 2.0],
            "string": ["foo", "bar"],
            "datetime": [
                Timestamp("2017-11-29 03:30:00"),
                Timestamp("2017-11-29 03:45:00"),
            ],
        }
    )
    result = df.apply(lambda row: (row.number, row.string), axis=1)
    expected = Series([(t.number, t.string) for t in df.itertuples()])
    tm.assert_series_equal(result, expected)


def test_infer_output_shape_listlike_columns():
    # GH 16353

    df = DataFrame(
        np.random.default_rng(2).standard_normal((6, 3)), columns=["A", "B", "C"]
    )

    result = df.apply(lambda x: [1, 2, 3], axis=1)
    expected = Series([[1, 2, 3] for t in df.itertuples()])
    tm.assert_series_equal(result, expected)

    result = df.apply(lambda x: [1, 2], axis=1)
    expected = Series([[1, 2] for t in df.itertuples()])
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("val", [1, 2])
def test_infer_output_shape_listlike_columns_np_func(val):
    # GH 17970
    df = DataFrame({"a": [1, 2, 3]}, index=list("abc"))

    result = df.apply(lambda row: np.ones(val), axis=1)
    expected = Series([np.ones(val) for t in df.itertuples()], index=df.index)
    tm.assert_series_equal(result, expected)


def test_infer_output_shape_listlike_columns_with_timestamp():
    # GH 17892
    df = DataFrame(
        {
            "a": [
                Timestamp("2010-02-01"),
                Timestamp("2010-02-04"),
                Timestamp("2010-02-05"),
                Timestamp("2010-02-06"),
            ],
            "b": [9, 5, 4, 3],
            "c": [5, 3, 4, 2],
            "d": [1, 2, 3, 4],
        }
    )

    def fun(x):
        return (1, 2)

    result = df.apply(fun, axis=1)
    expected = Series([(1, 2) for t in df.itertuples()])
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("lst", [[1, 2, 3], [1, 2]])
def test_consistent_coerce_for_shapes(lst):
    # we want column names to NOT be propagated
    # just because the shape matches the input shape
    df = DataFrame(
        np.random.default_rng(2).standard_normal((4, 3)), columns=["A", "B", "C"]
    )

    result = df.apply(lambda x: lst, axis=1)
    expected = Series([lst for t in df.itertuples()])
    tm.assert_series_equal(result, expected)


def test_consistent_names(int_frame_const_col):
    # if a Series is returned, we should use the resulting index names
    df = int_frame_const_col

    result = df.apply(
        lambda x: Series([1, 2, 3], index=["test", "other", "cols"]), axis=1
    )
    expected = int_frame_const_col.rename(
        columns={"A": "test", "B": "other", "C": "cols"}
    )
    tm.assert_frame_equal(result, expected)

    result = df.apply(lambda x: Series([1, 2], index=["test", "other"]), axis=1)
    expected = expected[["test", "other"]]
    tm.assert_frame_equal(result, expected)


def test_result_type(int_frame_const_col):
    # result_type should be consistent no matter which
    # path we take in the code
    df = int_frame_const_col

    result = df.apply(lambda x: [1, 2, 3], axis=1, result_type="expand")
    expected = df.copy()
    expected.columns = [0, 1, 2]
    tm.assert_frame_equal(result, expected)


def test_result_type_shorter_list(int_frame_const_col):
    # result_type should be consistent no matter which
    # path we take in the code
    df = int_frame_const_col
    result = df.apply(lambda x: [1, 2], axis=1, result_type="expand")
    expected = df[["A", "B"]].copy()
    expected.columns = [0, 1]
    tm.assert_frame_equal(result, expected)


def test_result_type_broadcast(int_frame_const_col, request, engine):
    # result_type should be consistent no matter which
    # path we take in the code
    if engine == "numba":
        mark = pytest.mark.xfail(reason="numba engine doesn't support list return")
        request.node.add_marker(mark)
    df = int_frame_const_col
    # broadcast result
    result = df.apply(
        lambda x: [1, 2, 3], axis=1, result_type="broadcast", engine=engine
    )
    expected = df.copy()
    tm.assert_frame_equal(result, expected)


def test_result_type_broadcast_series_func(int_frame_const_col, engine, request):
    # result_type should be consistent no matter which
    # path we take in the code
    if engine == "numba":
        mark = pytest.mark.xfail(
            reason="numba Series constructor only support ndarrays not list data"
        )
        request.node.add_marker(mark)
    df = int_frame_const_col
    columns = ["other", "col", "names"]
    result = df.apply(
        lambda x: Series([1, 2, 3], index=columns),
        axis=1,
        result_type="broadcast",
        engine=engine,
    )
    expected = df.copy()
    tm.assert_frame_equal(result, expected)


def test_result_type_series_result(int_frame_const_col, engine, request):
    # result_type should be consistent no matter which
    # path we take in the code
    if engine == "numba":
        mark = pytest.mark.xfail(
            reason="numba Series constructor only support ndarrays not list data"
        )
        request.node.add_marker(mark)
    df = int_frame_const_col
    # series result
    result = df.apply(lambda x: Series([1, 2, 3], index=x.index), axis=1, engine=engine)
    expected = df.copy()
    tm.assert_frame_equal(result, expected)


def test_result_type_series_result_other_index(int_frame_const_col, engine, request):
    # result_type should be consistent no matter which
    # path we take in the code

    if engine == "numba":
        mark = pytest.mark.xfail(
            reason="no support in numba Series constructor for list of columns"
        )
        request.node.add_marker(mark)
    df = int_frame_const_col
    # series result with other index
    columns = ["other", "col", "names"]
    result = df.apply(lambda x: Series([1, 2, 3], index=columns), axis=1, engine=engine)
    expected = df.copy()
    expected.columns = columns
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "box",
    [lambda x: list(x), lambda x: tuple(x), lambda x: np.array(x, dtype="int64")],
    ids=["list", "tuple", "array"],
)
def test_consistency_for_boxed(box, int_frame_const_col):
    # passing an array or list should not affect the output shape
    df = int_frame_const_col

    result = df.apply(lambda x: box([1, 2]), axis=1)
    expected = Series([box([1, 2]) for t in df.itertuples()])
    tm.assert_series_equal(result, expected)

    result = df.apply(lambda x: box([1, 2]), axis=1, result_type="expand")
    expected = int_frame_const_col[["A", "B"]].rename(columns={"A": 0, "B": 1})
    tm.assert_frame_equal(result, expected)


def test_agg_transform(axis, float_frame):
    other_axis = 1 if axis in {0, "index"} else 0

    with np.errstate(all="ignore"):
        f_abs = np.abs(float_frame)
        f_sqrt = np.sqrt(float_frame)

        # ufunc
        expected = f_sqrt.copy()
        result = float_frame.apply(np.sqrt, axis=axis)
        tm.assert_frame_equal(result, expected)

        # list-like
        result = float_frame.apply([np.sqrt], axis=axis)
        expected = f_sqrt.copy()
        if axis in {0, "index"}:
            expected.columns = MultiIndex.from_product([float_frame.columns, ["sqrt"]])
        else:
            expected.index = MultiIndex.from_product([float_frame.index, ["sqrt"]])
        tm.assert_frame_equal(result, expected)

        # multiple items in list
        # these are in the order as if we are applying both
        # functions per series and then concatting
        result = float_frame.apply([np.abs, np.sqrt], axis=axis)
        expected = zip_frames([f_abs, f_sqrt], axis=other_axis)
        if axis in {0, "index"}:
            expected.columns = MultiIndex.from_product(
                [float_frame.columns, ["absolute", "sqrt"]]
            )
        else:
            expected.index = MultiIndex.from_product(
                [float_frame.index, ["absolute", "sqrt"]]
            )
        tm.assert_frame_equal(result, expected)


def test_demo():
    # demonstration tests
    df = DataFrame({"A": range(5), "B": 5})

    result = df.agg(["min", "max"])
    expected = DataFrame(
        {"A": [0, 4], "B": [5, 5]}, columns=["A", "B"], index=["min", "max"]
    )
    tm.assert_frame_equal(result, expected)


def test_demo_dict_agg():
    # demonstration tests
    df = DataFrame({"A": range(5), "B": 5})
    result = df.agg({"A": ["min", "max"], "B": ["sum", "max"]})
    expected = DataFrame(
        {"A": [4.0, 0.0, np.nan], "B": [5.0, np.nan, 25.0]},
        columns=["A", "B"],
        index=["max", "min", "sum"],
    )
    tm.assert_frame_equal(result.reindex_like(expected), expected)


def test_agg_with_name_as_column_name():
    # GH 36212 - Column name is "name"
    data = {"name": ["foo", "bar"]}
    df = DataFrame(data)

    # result's name should be None
    result = df.agg({"name": "count"})
    expected = Series({"name": 2})
    tm.assert_series_equal(result, expected)

    # Check if name is still preserved when aggregating series instead
    result = df["name"].agg({"name": "count"})
    expected = Series({"name": 2}, name="name")
    tm.assert_series_equal(result, expected)


def test_agg_multiple_mixed():
    # GH 20909
    mdf = DataFrame(
        {
            "A": [1, 2, 3],
            "B": [1.0, 2.0, 3.0],
            "C": ["foo", "bar", "baz"],
        }
    )
    expected = DataFrame(
        {
            "A": [1, 6],
            "B": [1.0, 6.0],
            "C": ["bar", "foobarbaz"],
        },
        index=["min", "sum"],
    )
    # sorted index
    result = mdf.agg(["min", "sum"])
    tm.assert_frame_equal(result, expected)

    result = mdf[["C", "B", "A"]].agg(["sum", "min"])
    # GH40420: the result of .agg should have an index that is sorted
    # according to the arguments provided to agg.
    expected = expected[["C", "B", "A"]].reindex(["sum", "min"])
    tm.assert_frame_equal(result, expected)


def test_agg_multiple_mixed_raises():
    # GH 20909
    mdf = DataFrame(
        {
            "A": [1, 2, 3],
            "B": [1.0, 2.0, 3.0],
            "C": ["foo", "bar", "baz"],
            "D": date_range("20130101", periods=3),
        }
    )

    # sorted index
    msg = "does not support reduction"
    with pytest.raises(TypeError, match=msg):
        mdf.agg(["min", "sum"])

    with pytest.raises(TypeError, match=msg):
        mdf[["D", "C", "B", "A"]].agg(["sum", "min"])


def test_agg_reduce(axis, float_frame):
    other_axis = 1 if axis in {0, "index"} else 0
    name1, name2 = float_frame.axes[other_axis].unique()[:2].sort_values()

    # all reducers
    expected = pd.concat(
        [
            float_frame.mean(axis=axis),
            float_frame.max(axis=axis),
            float_frame.sum(axis=axis),
        ],
        axis=1,
    )
    expected.columns = ["mean", "max", "sum"]
    expected = expected.T if axis in {0, "index"} else expected

    result = float_frame.agg(["mean", "max", "sum"], axis=axis)
    tm.assert_frame_equal(result, expected)

    # dict input with scalars
    func = {name1: "mean", name2: "sum"}
    result = float_frame.agg(func, axis=axis)
    expected = Series(
        [
            float_frame.loc(other_axis)[name1].mean(),
            float_frame.loc(other_axis)[name2].sum(),
        ],
        index=[name1, name2],
    )
    tm.assert_series_equal(result, expected)

    # dict input with lists
    func = {name1: ["mean"], name2: ["sum"]}
    result = float_frame.agg(func, axis=axis)
    expected = DataFrame(
        {
            name1: Series([float_frame.loc(other_axis)[name1].mean()], index=["mean"]),
            name2: Series([float_frame.loc(other_axis)[name2].sum()], index=["sum"]),
        }
    )
    expected = expected.T if axis in {1, "columns"} else expected
    tm.assert_frame_equal(result, expected)

    # dict input with lists with multiple
    func = {name1: ["mean", "sum"], name2: ["sum", "max"]}
    result = float_frame.agg(func, axis=axis)
    expected = pd.concat(
        {
            name1: Series(
                [
                    float_frame.loc(other_axis)[name1].mean(),
                    float_frame.loc(other_axis)[name1].sum(),
                ],
                index=["mean", "sum"],
            ),
            name2: Series(
                [
                    float_frame.loc(other_axis)[name2].sum(),
                    float_frame.loc(other_axis)[name2].max(),
                ],
                index=["sum", "max"],
            ),
        },
        axis=1,
    )
    expected = expected.T if axis in {1, "columns"} else expected
    tm.assert_frame_equal(result, expected)


def test_nuiscance_columns():
    # GH 15015
    df = DataFrame(
        {
            "A": [1, 2, 3],
            "B": [1.0, 2.0, 3.0],
            "C": ["foo", "bar", "baz"],
            "D": date_range("20130101", periods=3),
        }
    )

    result = df.agg("min")
    expected = Series([1, 1.0, "bar", Timestamp("20130101")], index=df.columns)
    tm.assert_series_equal(result, expected)

    result = df.agg(["min"])
    expected = DataFrame(
        [[1, 1.0, "bar", Timestamp("20130101").as_unit("ns")]],
        index=["min"],
        columns=df.columns,
    )
    tm.assert_frame_equal(result, expected)

    msg = "does not support reduction"
    with pytest.raises(TypeError, match=msg):
        df.agg("sum")

    result = df[["A", "B", "C"]].agg("sum")
    expected = Series([6, 6.0, "foobarbaz"], index=["A", "B", "C"])
    tm.assert_series_equal(result, expected)

    msg = "does not support reduction"
    with pytest.raises(TypeError, match=msg):
        df.agg(["sum"])


@pytest.mark.parametrize("how", ["agg", "apply"])
def test_non_callable_aggregates(how):
    # GH 16405
    # 'size' is a property of frame/series
    # validate that this is working
    # GH 39116 - expand to apply
    df = DataFrame(
        {"A": [None, 2, 3], "B": [1.0, np.nan, 3.0], "C": ["foo", None, "bar"]}
    )

    # Function aggregate
    result = getattr(df, how)({"A": "count"})
    expected = Series({"A": 2})

    tm.assert_series_equal(result, expected)

    # Non-function aggregate
    result = getattr(df, how)({"A": "size"})
    expected = Series({"A": 3})

    tm.assert_series_equal(result, expected)

    # Mix function and non-function aggs
    result1 = getattr(df, how)(["count", "size"])
    result2 = getattr(df, how)(
        {"A": ["count", "size"], "B": ["count", "size"], "C": ["count", "size"]}
    )
    expected = DataFrame(
        {
            "A": {"count": 2, "size": 3},
            "B": {"count": 2, "size": 3},
            "C": {"count": 2, "size": 3},
        }
    )

    tm.assert_frame_equal(result1, result2, check_like=True)
    tm.assert_frame_equal(result2, expected, check_like=True)

    # Just functional string arg is same as calling df.arg()
    result = getattr(df, how)("count")
    expected = df.count()

    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("how", ["agg", "apply"])
def test_size_as_str(how, axis):
    # GH 39934
    df = DataFrame(
        {"A": [None, 2, 3], "B": [1.0, np.nan, 3.0], "C": ["foo", None, "bar"]}
    )
    # Just a string attribute arg same as calling df.arg
    # on the columns
    result = getattr(df, how)("size", axis=axis)
    if axis in (0, "index"):
        expected = Series(df.shape[0], index=df.columns)
    else:
        expected = Series(df.shape[1], index=df.index)
    tm.assert_series_equal(result, expected)


def test_agg_listlike_result():
    # GH-29587 user defined function returning list-likes
    df = DataFrame({"A": [2, 2, 3], "B": [1.5, np.nan, 1.5], "C": ["foo", None, "bar"]})

    def func(group_col):
        return list(group_col.dropna().unique())

    result = df.agg(func)
    expected = Series([[2, 3], [1.5], ["foo", "bar"]], index=["A", "B", "C"])
    tm.assert_series_equal(result, expected)

    result = df.agg([func])
    expected = expected.to_frame("func").T
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("axis", [0, 1])
@pytest.mark.parametrize(
    "args, kwargs",
    [
        ((1, 2, 3), {}),
        ((8, 7, 15), {}),
        ((1, 2), {}),
        ((1,), {"b": 2}),
        ((), {"a": 1, "b": 2}),
        ((), {"a": 2, "b": 1}),
        ((), {"a": 1, "b": 2, "c": 3}),
    ],
)
def test_agg_args_kwargs(axis, args, kwargs):
    def f(x, a, b, c=3):
        return x.sum() + (a + b) / c

    df = DataFrame([[1, 2], [3, 4]])

    if axis == 0:
        expected = Series([5.0, 7.0])
    else:
        expected = Series([4.0, 8.0])

    result = df.agg(f, axis, *args, **kwargs)

    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("num_cols", [2, 3, 5])
def test_frequency_is_original(num_cols, engine, request):
    # GH 22150
    if engine == "numba":
        mark = pytest.mark.xfail(reason="numba engine only supports numeric indices")
        request.node.add_marker(mark)
    index = pd.DatetimeIndex(["1950-06-30", "1952-10-24", "1953-05-29"])
    original = index.copy()
    df = DataFrame(1, index=index, columns=range(num_cols))
    df.apply(lambda x: x, engine=engine)
    assert index.freq == original.freq


def test_apply_datetime_tz_issue(engine, request):
    # GH 29052

    if engine == "numba":
        mark = pytest.mark.xfail(
            reason="numba engine doesn't support non-numeric indexes"
        )
        request.node.add_marker(mark)

    timestamps = [
        Timestamp("2019-03-15 12:34:31.909000+0000", tz="UTC"),
        Timestamp("2019-03-15 12:34:34.359000+0000", tz="UTC"),
        Timestamp("2019-03-15 12:34:34.660000+0000", tz="UTC"),
    ]
    df = DataFrame(data=[0, 1, 2], index=timestamps)
    result = df.apply(lambda x: x.name, axis=1, engine=engine)
    expected = Series(index=timestamps, data=timestamps)

    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("df", [DataFrame({"A": ["a", None], "B": ["c", "d"]})])
@pytest.mark.parametrize("method", ["min", "max", "sum"])
def test_mixed_column_raises(df, method, using_infer_string):
    # GH 16832
    if method == "sum":
        msg = r'can only concatenate str \(not "int"\) to str|does not support'
    else:
        msg = "not supported between instances of 'str' and 'float'"
    if not using_infer_string:
        with pytest.raises(TypeError, match=msg):
            getattr(df, method)()
    else:
        getattr(df, method)()


@pytest.mark.parametrize("col", [1, 1.0, True, "a", np.nan])
def test_apply_dtype(col):
    # GH 31466
    df = DataFrame([[1.0, col]], columns=["a", "b"])
    result = df.apply(lambda x: x.dtype)
    expected = df.dtypes

    tm.assert_series_equal(result, expected)


def test_apply_mutating(using_array_manager, using_copy_on_write, warn_copy_on_write):
    # GH#35462 case where applied func pins a new BlockManager to a row
    df = DataFrame({"a": range(100), "b": range(100, 200)})
    df_orig = df.copy()

    def func(row):
        mgr = row._mgr
        row.loc["a"] += 1
        assert row._mgr is not mgr
        return row

    expected = df.copy()
    expected["a"] += 1

    with tm.assert_cow_warning(warn_copy_on_write):
        result = df.apply(func, axis=1)

    tm.assert_frame_equal(result, expected)
    if using_copy_on_write or using_array_manager:
        # INFO(CoW) With copy on write, mutating a viewing row doesn't mutate the parent
        # INFO(ArrayManager) With BlockManager, the row is a view and mutated in place,
        # with ArrayManager the row is not a view, and thus not mutated in place
        tm.assert_frame_equal(df, df_orig)
    else:
        tm.assert_frame_equal(df, result)


def test_apply_empty_list_reduce():
    # GH#35683 get columns correct
    df = DataFrame([[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]], columns=["a", "b"])

    result = df.apply(lambda x: [], result_type="reduce")
    expected = Series({"a": [], "b": []}, dtype=object)
    tm.assert_series_equal(result, expected)


def test_apply_no_suffix_index(engine, request):
    # GH36189
    if engine == "numba":
        mark = pytest.mark.xfail(
            reason="numba engine doesn't support list-likes/dict-like callables"
        )
        request.node.add_marker(mark)
    pdf = DataFrame([[4, 9]] * 3, columns=["A", "B"])
    result = pdf.apply(["sum", lambda x: x.sum(), lambda x: x.sum()], engine=engine)
    expected = DataFrame(
        {"A": [12, 12, 12], "B": [27, 27, 27]}, index=["sum", "<lambda>", "<lambda>"]
    )

    tm.assert_frame_equal(result, expected)


def test_apply_raw_returns_string(engine):
    # https://github.com/pandas-dev/pandas/issues/35940
    if engine == "numba":
        pytest.skip("No object dtype support in numba")
    df = DataFrame({"A": ["aa", "bbb"]})
    result = df.apply(lambda x: x[0], engine=engine, axis=1, raw=True)
    expected = Series(["aa", "bbb"])
    tm.assert_series_equal(result, expected)


def test_aggregation_func_column_order():
    # GH40420: the result of .agg should have an index that is sorted
    # according to the arguments provided to agg.
    df = DataFrame(
        [
            (1, 0, 0),
            (2, 0, 0),
            (3, 0, 0),
            (4, 5, 4),
            (5, 6, 6),
            (6, 7, 7),
        ],
        columns=("att1", "att2", "att3"),
    )

    def sum_div2(s):
        return s.sum() / 2

    aggs = ["sum", sum_div2, "count", "min"]
    result = df.agg(aggs)
    expected = DataFrame(
        {
            "att1": [21.0, 10.5, 6.0, 1.0],
            "att2": [18.0, 9.0, 6.0, 0.0],
            "att3": [17.0, 8.5, 6.0, 0.0],
        },
        index=["sum", "sum_div2", "count", "min"],
    )
    tm.assert_frame_equal(result, expected)


def test_apply_getitem_axis_1(engine, request):
    # GH 13427
    if engine == "numba":
        mark = pytest.mark.xfail(
            reason="numba engine not supporting duplicate index values"
        )
        request.node.add_marker(mark)
    df = DataFrame({"a": [0, 1, 2], "b": [1, 2, 3]})
    result = df[["a", "a"]].apply(
        lambda x: x.iloc[0] + x.iloc[1], axis=1, engine=engine
    )
    expected = Series([0, 2, 4])
    tm.assert_series_equal(result, expected)


def test_nuisance_depr_passes_through_warnings():
    # GH 43740
    # DataFrame.agg with list-likes may emit warnings for both individual
    # args and for entire columns, but we only want to emit once. We
    # catch and suppress the warnings for individual args, but need to make
    # sure if some other warnings were raised, they get passed through to
    # the user.

    def expected_warning(x):
        warnings.warn("Hello, World!")
        return x.sum()

    df = DataFrame({"a": [1, 2, 3]})
    with tm.assert_produces_warning(UserWarning, match="Hello, World!"):
        df.agg([expected_warning])


def test_apply_type():
    # GH 46719
    df = DataFrame(
        {"col1": [3, "string", float], "col2": [0.25, datetime(2020, 1, 1), np.nan]},
        index=["a", "b", "c"],
    )

    # axis=0
    result = df.apply(type, axis=0)
    expected = Series({"col1": Series, "col2": Series})
    tm.assert_series_equal(result, expected)

    # axis=1
    result = df.apply(type, axis=1)
    expected = Series({"a": Series, "b": Series, "c": Series})
    tm.assert_series_equal(result, expected)


def test_apply_on_empty_dataframe(engine):
    # GH 39111
    df = DataFrame({"a": [1, 2], "b": [3, 0]})
    result = df.head(0).apply(lambda x: max(x["a"], x["b"]), axis=1, engine=engine)
    expected = Series([], dtype=np.float64)
    tm.assert_series_equal(result, expected)


def test_apply_return_list():
    df = DataFrame({"a": [1, 2], "b": [2, 3]})
    result = df.apply(lambda x: [x.values])
    expected = DataFrame({"a": [[1, 2]], "b": [[2, 3]]})
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "test, constant",
    [
        ({"a": [1, 2, 3], "b": [1, 1, 1]}, {"a": [1, 2, 3], "b": [1]}),
        ({"a": [2, 2, 2], "b": [1, 1, 1]}, {"a": [2], "b": [1]}),
    ],
)
def test_unique_agg_type_is_series(test, constant):
    # GH#22558
    df1 = DataFrame(test)
    expected = Series(data=constant, index=["a", "b"], dtype="object")
    aggregation = {"a": "unique", "b": "unique"}

    result = df1.agg(aggregation)

    tm.assert_series_equal(result, expected)


def test_any_apply_keyword_non_zero_axis_regression():
    # https://github.com/pandas-dev/pandas/issues/48656
    df = DataFrame({"A": [1, 2, 0], "B": [0, 2, 0], "C": [0, 0, 0]})
    expected = Series([True, True, False])
    tm.assert_series_equal(df.any(axis=1), expected)

    result = df.apply("any", axis=1)
    tm.assert_series_equal(result, expected)

    result = df.apply("any", 1)
    tm.assert_series_equal(result, expected)


def test_agg_mapping_func_deprecated():
    # GH 53325
    df = DataFrame({"x": [1, 2, 3]})

    def foo1(x, a=1, c=0):
        return x + a + c

    def foo2(x, b=2, c=0):
        return x + b + c

    # single func already takes the vectorized path
    result = df.agg(foo1, 0, 3, c=4)
    expected = df + 7
    tm.assert_frame_equal(result, expected)

    msg = "using .+ in Series.agg cannot aggregate and"

    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = df.agg([foo1, foo2], 0, 3, c=4)
    expected = DataFrame(
        [[8, 8], [9, 9], [10, 10]], columns=[["x", "x"], ["foo1", "foo2"]]
    )
    tm.assert_frame_equal(result, expected)

    # TODO: the result below is wrong, should be fixed (GH53325)
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = df.agg({"x": foo1}, 0, 3, c=4)
    expected = DataFrame([2, 3, 4], columns=["x"])
    tm.assert_frame_equal(result, expected)


def test_agg_std():
    df = DataFrame(np.arange(6).reshape(3, 2), columns=["A", "B"])

    with tm.assert_produces_warning(FutureWarning, match="using DataFrame.std"):
        result = df.agg(np.std)
    expected = Series({"A": 2.0, "B": 2.0}, dtype=float)
    tm.assert_series_equal(result, expected)

    with tm.assert_produces_warning(FutureWarning, match="using Series.std"):
        result = df.agg([np.std])
    expected = DataFrame({"A": 2.0, "B": 2.0}, index=["std"])
    tm.assert_frame_equal(result, expected)


def test_agg_dist_like_and_nonunique_columns():
    # GH#51099
    df = DataFrame(
        {"A": [None, 2, 3], "B": [1.0, np.nan, 3.0], "C": ["foo", None, "bar"]}
    )
    df.columns = ["A", "A", "C"]

    result = df.agg({"A": "count"})
    expected = df["A"].count()
    tm.assert_series_equal(result, expected)
