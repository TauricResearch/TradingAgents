import numpy as np
import pytest

from pandas.compat import is_platform_arm
from pandas.errors import NumbaUtilError

from pandas import (
    DataFrame,
    Index,
    NamedAgg,
    Series,
    option_context,
)
import pandas._testing as tm
from pandas.util.version import Version

pytestmark = [pytest.mark.single_cpu]

numba = pytest.importorskip("numba")
pytestmark.append(
    pytest.mark.skipif(
        Version(numba.__version__) == Version("0.61") and is_platform_arm(),
        reason=f"Segfaults on ARM platforms with numba {numba.__version__}",
    )
)


def test_correct_function_signature():
    pytest.importorskip("numba")

    def incorrect_function(x):
        return sum(x) * 2.7

    data = DataFrame(
        {"key": ["a", "a", "b", "b", "a"], "data": [1.0, 2.0, 3.0, 4.0, 5.0]},
        columns=["key", "data"],
    )
    with pytest.raises(NumbaUtilError, match="The first 2"):
        data.groupby("key").agg(incorrect_function, engine="numba")

    with pytest.raises(NumbaUtilError, match="The first 2"):
        data.groupby("key")["data"].agg(incorrect_function, engine="numba")


def test_check_nopython_kwargs():
    pytest.importorskip("numba")

    def incorrect_function(values, index):
        return sum(values) * 2.7

    data = DataFrame(
        {"key": ["a", "a", "b", "b", "a"], "data": [1.0, 2.0, 3.0, 4.0, 5.0]},
        columns=["key", "data"],
    )
    with pytest.raises(NumbaUtilError, match="numba does not support"):
        data.groupby("key").agg(incorrect_function, engine="numba", a=1)

    with pytest.raises(NumbaUtilError, match="numba does not support"):
        data.groupby("key")["data"].agg(incorrect_function, engine="numba", a=1)


@pytest.mark.filterwarnings("ignore")
# Filter warnings when parallel=True and the function can't be parallelized by Numba
@pytest.mark.parametrize("jit", [True, False])
@pytest.mark.parametrize("pandas_obj", ["Series", "DataFrame"])
@pytest.mark.parametrize("as_index", [True, False])
def test_numba_vs_cython(jit, pandas_obj, nogil, parallel, nopython, as_index):
    pytest.importorskip("numba")

    def func_numba(values, index):
        return np.mean(values) * 2.7

    if jit:
        # Test accepted jitted functions
        import numba

        func_numba = numba.jit(func_numba)

    data = DataFrame(
        {0: ["a", "a", "b", "b", "a"], 1: [1.0, 2.0, 3.0, 4.0, 5.0]}, columns=[0, 1]
    )
    engine_kwargs = {"nogil": nogil, "parallel": parallel, "nopython": nopython}
    grouped = data.groupby(0, as_index=as_index)
    if pandas_obj == "Series":
        grouped = grouped[1]

    result = grouped.agg(func_numba, engine="numba", engine_kwargs=engine_kwargs)
    expected = grouped.agg(lambda x: np.mean(x) * 2.7, engine="cython")

    tm.assert_equal(result, expected)


@pytest.mark.filterwarnings("ignore")
# Filter warnings when parallel=True and the function can't be parallelized by Numba
@pytest.mark.parametrize("jit", [True, False])
@pytest.mark.parametrize("pandas_obj", ["Series", "DataFrame"])
def test_cache(jit, pandas_obj, nogil, parallel, nopython):
    # Test that the functions are cached correctly if we switch functions
    pytest.importorskip("numba")

    def func_1(values, index):
        return np.mean(values) - 3.4

    def func_2(values, index):
        return np.mean(values) * 2.7

    if jit:
        import numba

        func_1 = numba.jit(func_1)
        func_2 = numba.jit(func_2)

    data = DataFrame(
        {0: ["a", "a", "b", "b", "a"], 1: [1.0, 2.0, 3.0, 4.0, 5.0]}, columns=[0, 1]
    )
    engine_kwargs = {"nogil": nogil, "parallel": parallel, "nopython": nopython}
    grouped = data.groupby(0)
    if pandas_obj == "Series":
        grouped = grouped[1]

    result = grouped.agg(func_1, engine="numba", engine_kwargs=engine_kwargs)
    expected = grouped.agg(lambda x: np.mean(x) - 3.4, engine="cython")
    tm.assert_equal(result, expected)

    # Add func_2 to the cache
    result = grouped.agg(func_2, engine="numba", engine_kwargs=engine_kwargs)
    expected = grouped.agg(lambda x: np.mean(x) * 2.7, engine="cython")
    tm.assert_equal(result, expected)

    # Retest func_1 which should use the cache
    result = grouped.agg(func_1, engine="numba", engine_kwargs=engine_kwargs)
    expected = grouped.agg(lambda x: np.mean(x) - 3.4, engine="cython")
    tm.assert_equal(result, expected)


def test_use_global_config():
    pytest.importorskip("numba")

    def func_1(values, index):
        return np.mean(values) - 3.4

    data = DataFrame(
        {0: ["a", "a", "b", "b", "a"], 1: [1.0, 2.0, 3.0, 4.0, 5.0]}, columns=[0, 1]
    )
    grouped = data.groupby(0)
    expected = grouped.agg(func_1, engine="numba")
    with option_context("compute.use_numba", True):
        result = grouped.agg(func_1, engine=None)
    tm.assert_frame_equal(expected, result)


@pytest.mark.parametrize(
    "agg_kwargs",
    [
        {"func": ["min", "max"]},
        {"func": "min"},
        {"func": {1: ["min", "max"], 2: "sum"}},
        {"bmin": NamedAgg(column=1, aggfunc="min")},
    ],
)
def test_multifunc_numba_vs_cython_frame(agg_kwargs):
    pytest.importorskip("numba")
    data = DataFrame(
        {
            0: ["a", "a", "b", "b", "a"],
            1: [1.0, 2.0, 3.0, 4.0, 5.0],
            2: [1, 2, 3, 4, 5],
        },
        columns=[0, 1, 2],
    )
    grouped = data.groupby(0)
    result = grouped.agg(**agg_kwargs, engine="numba")
    expected = grouped.agg(**agg_kwargs, engine="cython")
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "agg_kwargs,expected_func",
    [
        ({"func": lambda values, index: values.sum()}, "sum"),
        # FIXME
        pytest.param(
            {
                "func": [
                    lambda values, index: values.sum(),
                    lambda values, index: values.min(),
                ]
            },
            ["sum", "min"],
            marks=pytest.mark.xfail(
                reason="This doesn't work yet! Fails in nopython pipeline!"
            ),
        ),
    ],
)
def test_multifunc_numba_udf_frame(agg_kwargs, expected_func):
    pytest.importorskip("numba")
    data = DataFrame(
        {
            0: ["a", "a", "b", "b", "a"],
            1: [1.0, 2.0, 3.0, 4.0, 5.0],
            2: [1, 2, 3, 4, 5],
        },
        columns=[0, 1, 2],
    )
    grouped = data.groupby(0)
    result = grouped.agg(**agg_kwargs, engine="numba")
    expected = grouped.agg(expected_func, engine="cython")
    # check_dtype can be removed if GH 44952 is addressed
    # Currently, UDFs still always return float64 while reductions can preserve dtype
    tm.assert_frame_equal(result, expected, check_dtype=False)


@pytest.mark.parametrize(
    "agg_kwargs",
    [{"func": ["min", "max"]}, {"func": "min"}, {"min_val": "min", "max_val": "max"}],
)
def test_multifunc_numba_vs_cython_series(agg_kwargs):
    pytest.importorskip("numba")
    labels = ["a", "a", "b", "b", "a"]
    data = Series([1.0, 2.0, 3.0, 4.0, 5.0])
    grouped = data.groupby(labels)
    agg_kwargs["engine"] = "numba"
    result = grouped.agg(**agg_kwargs)
    agg_kwargs["engine"] = "cython"
    expected = grouped.agg(**agg_kwargs)
    if isinstance(expected, DataFrame):
        tm.assert_frame_equal(result, expected)
    else:
        tm.assert_series_equal(result, expected)


@pytest.mark.single_cpu
@pytest.mark.parametrize(
    "data,agg_kwargs",
    [
        (Series([1.0, 2.0, 3.0, 4.0, 5.0]), {"func": ["min", "max"]}),
        (Series([1.0, 2.0, 3.0, 4.0, 5.0]), {"func": "min"}),
        (
            DataFrame(
                {1: [1.0, 2.0, 3.0, 4.0, 5.0], 2: [1, 2, 3, 4, 5]}, columns=[1, 2]
            ),
            {"func": ["min", "max"]},
        ),
        (
            DataFrame(
                {1: [1.0, 2.0, 3.0, 4.0, 5.0], 2: [1, 2, 3, 4, 5]}, columns=[1, 2]
            ),
            {"func": "min"},
        ),
        (
            DataFrame(
                {1: [1.0, 2.0, 3.0, 4.0, 5.0], 2: [1, 2, 3, 4, 5]}, columns=[1, 2]
            ),
            {"func": {1: ["min", "max"], 2: "sum"}},
        ),
        (
            DataFrame(
                {1: [1.0, 2.0, 3.0, 4.0, 5.0], 2: [1, 2, 3, 4, 5]}, columns=[1, 2]
            ),
            {"min_col": NamedAgg(column=1, aggfunc="min")},
        ),
    ],
)
def test_multifunc_numba_kwarg_propagation(data, agg_kwargs):
    pytest.importorskip("numba")
    labels = ["a", "a", "b", "b", "a"]
    grouped = data.groupby(labels)
    result = grouped.agg(**agg_kwargs, engine="numba", engine_kwargs={"parallel": True})
    expected = grouped.agg(**agg_kwargs, engine="numba")
    if isinstance(expected, DataFrame):
        tm.assert_frame_equal(result, expected)
    else:
        tm.assert_series_equal(result, expected)


def test_args_not_cached():
    # GH 41647
    pytest.importorskip("numba")

    def sum_last(values, index, n):
        return values[-n:].sum()

    df = DataFrame({"id": [0, 0, 1, 1], "x": [1, 1, 1, 1]})
    grouped_x = df.groupby("id")["x"]
    result = grouped_x.agg(sum_last, 1, engine="numba")
    expected = Series([1.0] * 2, name="x", index=Index([0, 1], name="id"))
    tm.assert_series_equal(result, expected)

    result = grouped_x.agg(sum_last, 2, engine="numba")
    expected = Series([2.0] * 2, name="x", index=Index([0, 1], name="id"))
    tm.assert_series_equal(result, expected)


def test_index_data_correctly_passed():
    # GH 43133
    pytest.importorskip("numba")

    def f(values, index):
        return np.mean(index)

    df = DataFrame({"group": ["A", "A", "B"], "v": [4, 5, 6]}, index=[-1, -2, -3])
    result = df.groupby("group").aggregate(f, engine="numba")
    expected = DataFrame(
        [-1.5, -3.0], columns=["v"], index=Index(["A", "B"], name="group")
    )
    tm.assert_frame_equal(result, expected)


def test_engine_kwargs_not_cached():
    # If the user passes a different set of engine_kwargs don't return the same
    # jitted function
    pytest.importorskip("numba")
    nogil = True
    parallel = False
    nopython = True

    def func_kwargs(values, index):
        return nogil + parallel + nopython

    engine_kwargs = {"nopython": nopython, "nogil": nogil, "parallel": parallel}
    df = DataFrame({"value": [0, 0, 0]})
    result = df.groupby(level=0).aggregate(
        func_kwargs, engine="numba", engine_kwargs=engine_kwargs
    )
    expected = DataFrame({"value": [2.0, 2.0, 2.0]})
    tm.assert_frame_equal(result, expected)

    nogil = False
    engine_kwargs = {"nopython": nopython, "nogil": nogil, "parallel": parallel}
    result = df.groupby(level=0).aggregate(
        func_kwargs, engine="numba", engine_kwargs=engine_kwargs
    )
    expected = DataFrame({"value": [1.0, 1.0, 1.0]})
    tm.assert_frame_equal(result, expected)


@pytest.mark.filterwarnings("ignore")
def test_multiindex_one_key(nogil, parallel, nopython):
    pytest.importorskip("numba")

    def numba_func(values, index):
        return 1

    df = DataFrame([{"A": 1, "B": 2, "C": 3}]).set_index(["A", "B"])
    engine_kwargs = {"nopython": nopython, "nogil": nogil, "parallel": parallel}
    result = df.groupby("A").agg(
        numba_func, engine="numba", engine_kwargs=engine_kwargs
    )
    expected = DataFrame([1.0], index=Index([1], name="A"), columns=["C"])
    tm.assert_frame_equal(result, expected)


def test_multiindex_multi_key_not_supported(nogil, parallel, nopython):
    pytest.importorskip("numba")

    def numba_func(values, index):
        return 1

    df = DataFrame([{"A": 1, "B": 2, "C": 3}]).set_index(["A", "B"])
    engine_kwargs = {"nopython": nopython, "nogil": nogil, "parallel": parallel}
    with pytest.raises(NotImplementedError, match="more than 1 grouping labels"):
        df.groupby(["A", "B"]).agg(
            numba_func, engine="numba", engine_kwargs=engine_kwargs
        )


def test_multilabel_numba_vs_cython(numba_supported_reductions):
    pytest.importorskip("numba")
    reduction, kwargs = numba_supported_reductions
    df = DataFrame(
        {
            "A": ["foo", "bar", "foo", "bar", "foo", "bar", "foo", "foo"],
            "B": ["one", "one", "two", "three", "two", "two", "one", "three"],
            "C": np.random.default_rng(2).standard_normal(8),
            "D": np.random.default_rng(2).standard_normal(8),
        }
    )
    gb = df.groupby(["A", "B"])
    res_agg = gb.agg(reduction, engine="numba", **kwargs)
    expected_agg = gb.agg(reduction, engine="cython", **kwargs)
    tm.assert_frame_equal(res_agg, expected_agg)
    # Test that calling the aggregation directly also works
    direct_res = getattr(gb, reduction)(engine="numba", **kwargs)
    direct_expected = getattr(gb, reduction)(engine="cython", **kwargs)
    tm.assert_frame_equal(direct_res, direct_expected)


def test_multilabel_udf_numba_vs_cython():
    pytest.importorskip("numba")
    df = DataFrame(
        {
            "A": ["foo", "bar", "foo", "bar", "foo", "bar", "foo", "foo"],
            "B": ["one", "one", "two", "three", "two", "two", "one", "three"],
            "C": np.random.default_rng(2).standard_normal(8),
            "D": np.random.default_rng(2).standard_normal(8),
        }
    )
    gb = df.groupby(["A", "B"])
    result = gb.agg(lambda values, index: values.min(), engine="numba")
    expected = gb.agg(lambda x: x.min(), engine="cython")
    tm.assert_frame_equal(result, expected)
