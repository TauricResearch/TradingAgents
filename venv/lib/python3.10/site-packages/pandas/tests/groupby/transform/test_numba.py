import numpy as np
import pytest

from pandas.compat import is_platform_arm
from pandas.errors import NumbaUtilError

from pandas import (
    DataFrame,
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
        return x + 1

    data = DataFrame(
        {"key": ["a", "a", "b", "b", "a"], "data": [1.0, 2.0, 3.0, 4.0, 5.0]},
        columns=["key", "data"],
    )
    with pytest.raises(NumbaUtilError, match="The first 2"):
        data.groupby("key").transform(incorrect_function, engine="numba")

    with pytest.raises(NumbaUtilError, match="The first 2"):
        data.groupby("key")["data"].transform(incorrect_function, engine="numba")


def test_check_nopython_kwargs():
    pytest.importorskip("numba")

    def incorrect_function(values, index):
        return values + 1

    data = DataFrame(
        {"key": ["a", "a", "b", "b", "a"], "data": [1.0, 2.0, 3.0, 4.0, 5.0]},
        columns=["key", "data"],
    )
    with pytest.raises(NumbaUtilError, match="numba does not support"):
        data.groupby("key").transform(incorrect_function, engine="numba", a=1)

    with pytest.raises(NumbaUtilError, match="numba does not support"):
        data.groupby("key")["data"].transform(incorrect_function, engine="numba", a=1)


@pytest.mark.filterwarnings("ignore")
# Filter warnings when parallel=True and the function can't be parallelized by Numba
@pytest.mark.parametrize("jit", [True, False])
@pytest.mark.parametrize("pandas_obj", ["Series", "DataFrame"])
@pytest.mark.parametrize("as_index", [True, False])
def test_numba_vs_cython(jit, pandas_obj, nogil, parallel, nopython, as_index):
    pytest.importorskip("numba")

    def func(values, index):
        return values + 1

    if jit:
        # Test accepted jitted functions
        import numba

        func = numba.jit(func)

    data = DataFrame(
        {0: ["a", "a", "b", "b", "a"], 1: [1.0, 2.0, 3.0, 4.0, 5.0]}, columns=[0, 1]
    )
    engine_kwargs = {"nogil": nogil, "parallel": parallel, "nopython": nopython}
    grouped = data.groupby(0, as_index=as_index)
    if pandas_obj == "Series":
        grouped = grouped[1]

    result = grouped.transform(func, engine="numba", engine_kwargs=engine_kwargs)
    expected = grouped.transform(lambda x: x + 1, engine="cython")

    tm.assert_equal(result, expected)


@pytest.mark.filterwarnings("ignore")
# Filter warnings when parallel=True and the function can't be parallelized by Numba
@pytest.mark.parametrize("jit", [True, False])
@pytest.mark.parametrize("pandas_obj", ["Series", "DataFrame"])
def test_cache(jit, pandas_obj, nogil, parallel, nopython):
    # Test that the functions are cached correctly if we switch functions
    pytest.importorskip("numba")

    def func_1(values, index):
        return values + 1

    def func_2(values, index):
        return values * 5

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

    result = grouped.transform(func_1, engine="numba", engine_kwargs=engine_kwargs)
    expected = grouped.transform(lambda x: x + 1, engine="cython")
    tm.assert_equal(result, expected)

    result = grouped.transform(func_2, engine="numba", engine_kwargs=engine_kwargs)
    expected = grouped.transform(lambda x: x * 5, engine="cython")
    tm.assert_equal(result, expected)

    # Retest func_1 which should use the cache
    result = grouped.transform(func_1, engine="numba", engine_kwargs=engine_kwargs)
    expected = grouped.transform(lambda x: x + 1, engine="cython")
    tm.assert_equal(result, expected)


def test_use_global_config():
    pytest.importorskip("numba")

    def func_1(values, index):
        return values + 1

    data = DataFrame(
        {0: ["a", "a", "b", "b", "a"], 1: [1.0, 2.0, 3.0, 4.0, 5.0]}, columns=[0, 1]
    )
    grouped = data.groupby(0)
    expected = grouped.transform(func_1, engine="numba")
    with option_context("compute.use_numba", True):
        result = grouped.transform(func_1, engine=None)
    tm.assert_frame_equal(expected, result)


# TODO: Test more than just reductions (e.g. actually test transformations once we have
@pytest.mark.parametrize(
    "agg_func", [["min", "max"], "min", {"B": ["min", "max"], "C": "sum"}]
)
def test_string_cython_vs_numba(agg_func, numba_supported_reductions):
    pytest.importorskip("numba")
    agg_func, kwargs = numba_supported_reductions
    data = DataFrame(
        {0: ["a", "a", "b", "b", "a"], 1: [1.0, 2.0, 3.0, 4.0, 5.0]}, columns=[0, 1]
    )
    grouped = data.groupby(0)

    result = grouped.transform(agg_func, engine="numba", **kwargs)
    expected = grouped.transform(agg_func, engine="cython", **kwargs)
    tm.assert_frame_equal(result, expected)

    result = grouped[1].transform(agg_func, engine="numba", **kwargs)
    expected = grouped[1].transform(agg_func, engine="cython", **kwargs)
    tm.assert_series_equal(result, expected)


def test_args_not_cached():
    # GH 41647
    pytest.importorskip("numba")

    def sum_last(values, index, n):
        return values[-n:].sum()

    df = DataFrame({"id": [0, 0, 1, 1], "x": [1, 1, 1, 1]})
    grouped_x = df.groupby("id")["x"]
    result = grouped_x.transform(sum_last, 1, engine="numba")
    expected = Series([1.0] * 4, name="x")
    tm.assert_series_equal(result, expected)

    result = grouped_x.transform(sum_last, 2, engine="numba")
    expected = Series([2.0] * 4, name="x")
    tm.assert_series_equal(result, expected)


def test_index_data_correctly_passed():
    # GH 43133
    pytest.importorskip("numba")

    def f(values, index):
        return index - 1

    df = DataFrame({"group": ["A", "A", "B"], "v": [4, 5, 6]}, index=[-1, -2, -3])
    result = df.groupby("group").transform(f, engine="numba")
    expected = DataFrame([-4.0, -3.0, -2.0], columns=["v"], index=[-1, -2, -3])
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
    result = df.groupby(level=0).transform(
        func_kwargs, engine="numba", engine_kwargs=engine_kwargs
    )
    expected = DataFrame({"value": [2.0, 2.0, 2.0]})
    tm.assert_frame_equal(result, expected)

    nogil = False
    engine_kwargs = {"nopython": nopython, "nogil": nogil, "parallel": parallel}
    result = df.groupby(level=0).transform(
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
    result = df.groupby("A").transform(
        numba_func, engine="numba", engine_kwargs=engine_kwargs
    )
    expected = DataFrame([{"A": 1, "B": 2, "C": 1.0}]).set_index(["A", "B"])
    tm.assert_frame_equal(result, expected)


def test_multiindex_multi_key_not_supported(nogil, parallel, nopython):
    pytest.importorskip("numba")

    def numba_func(values, index):
        return 1

    df = DataFrame([{"A": 1, "B": 2, "C": 3}]).set_index(["A", "B"])
    engine_kwargs = {"nopython": nopython, "nogil": nogil, "parallel": parallel}
    with pytest.raises(NotImplementedError, match="more than 1 grouping labels"):
        df.groupby(["A", "B"]).transform(
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
    res_agg = gb.transform(reduction, engine="numba", **kwargs)
    expected_agg = gb.transform(reduction, engine="cython", **kwargs)
    tm.assert_frame_equal(res_agg, expected_agg)


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
    result = gb.transform(
        lambda values, index: (values - values.min()) / (values.max() - values.min()),
        engine="numba",
    )
    expected = gb.transform(
        lambda x: (x - x.min()) / (x.max() - x.min()), engine="cython"
    )
    tm.assert_frame_equal(result, expected)
