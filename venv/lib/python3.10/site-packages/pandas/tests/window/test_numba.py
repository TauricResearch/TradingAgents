import numpy as np
import pytest

from pandas.compat import is_platform_arm
from pandas.errors import NumbaUtilError
import pandas.util._test_decorators as td

from pandas import (
    DataFrame,
    Series,
    option_context,
    to_datetime,
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


@pytest.fixture(params=["single", "table"])
def method(request):
    """method keyword in rolling/expanding/ewm constructor"""
    return request.param


@pytest.fixture(
    params=[
        ["sum", {}],
        ["mean", {}],
        ["median", {}],
        ["max", {}],
        ["min", {}],
        ["var", {}],
        ["var", {"ddof": 0}],
        ["std", {}],
        ["std", {"ddof": 0}],
    ]
)
def arithmetic_numba_supported_operators(request):
    return request.param


@td.skip_if_no("numba")
@pytest.mark.filterwarnings("ignore")
# Filter warnings when parallel=True and the function can't be parallelized by Numba
class TestEngine:
    @pytest.mark.parametrize("jit", [True, False])
    def test_numba_vs_cython_apply(self, jit, nogil, parallel, nopython, center, step):
        def f(x, *args):
            arg_sum = 0
            for arg in args:
                arg_sum += arg
            return np.mean(x) + arg_sum

        if jit:
            import numba

            f = numba.jit(f)

        engine_kwargs = {"nogil": nogil, "parallel": parallel, "nopython": nopython}
        args = (2,)

        s = Series(range(10))
        result = s.rolling(2, center=center, step=step).apply(
            f, args=args, engine="numba", engine_kwargs=engine_kwargs, raw=True
        )
        expected = s.rolling(2, center=center, step=step).apply(
            f, engine="cython", args=args, raw=True
        )
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "data",
        [
            DataFrame(np.eye(5)),
            DataFrame(
                [
                    [5, 7, 7, 7, np.nan, np.inf, 4, 3, 3, 3],
                    [5, 7, 7, 7, np.nan, np.inf, 7, 3, 3, 3],
                    [np.nan, np.nan, 5, 6, 7, 5, 5, 5, 5, 5],
                ]
            ).T,
            Series(range(5), name="foo"),
            Series([20, 10, 10, np.inf, 1, 1, 2, 3]),
            Series([20, 10, 10, np.nan, 10, 1, 2, 3]),
        ],
    )
    def test_numba_vs_cython_rolling_methods(
        self,
        data,
        nogil,
        parallel,
        nopython,
        arithmetic_numba_supported_operators,
        step,
    ):
        method, kwargs = arithmetic_numba_supported_operators

        engine_kwargs = {"nogil": nogil, "parallel": parallel, "nopython": nopython}

        roll = data.rolling(3, step=step)
        result = getattr(roll, method)(
            engine="numba", engine_kwargs=engine_kwargs, **kwargs
        )
        expected = getattr(roll, method)(engine="cython", **kwargs)
        tm.assert_equal(result, expected)

    @pytest.mark.parametrize(
        "data", [DataFrame(np.eye(5)), Series(range(5), name="foo")]
    )
    def test_numba_vs_cython_expanding_methods(
        self, data, nogil, parallel, nopython, arithmetic_numba_supported_operators
    ):
        method, kwargs = arithmetic_numba_supported_operators

        engine_kwargs = {"nogil": nogil, "parallel": parallel, "nopython": nopython}

        data = DataFrame(np.eye(5))
        expand = data.expanding()
        result = getattr(expand, method)(
            engine="numba", engine_kwargs=engine_kwargs, **kwargs
        )
        expected = getattr(expand, method)(engine="cython", **kwargs)
        tm.assert_equal(result, expected)

    @pytest.mark.parametrize("jit", [True, False])
    def test_cache_apply(self, jit, nogil, parallel, nopython, step):
        # Test that the functions are cached correctly if we switch functions
        def func_1(x):
            return np.mean(x) + 4

        def func_2(x):
            return np.std(x) * 5

        if jit:
            import numba

            func_1 = numba.jit(func_1)
            func_2 = numba.jit(func_2)

        engine_kwargs = {"nogil": nogil, "parallel": parallel, "nopython": nopython}

        roll = Series(range(10)).rolling(2, step=step)
        result = roll.apply(
            func_1, engine="numba", engine_kwargs=engine_kwargs, raw=True
        )
        expected = roll.apply(func_1, engine="cython", raw=True)
        tm.assert_series_equal(result, expected)

        result = roll.apply(
            func_2, engine="numba", engine_kwargs=engine_kwargs, raw=True
        )
        expected = roll.apply(func_2, engine="cython", raw=True)
        tm.assert_series_equal(result, expected)
        # This run should use the cached func_1
        result = roll.apply(
            func_1, engine="numba", engine_kwargs=engine_kwargs, raw=True
        )
        expected = roll.apply(func_1, engine="cython", raw=True)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "window,window_kwargs",
        [
            ["rolling", {"window": 3, "min_periods": 0}],
            ["expanding", {}],
        ],
    )
    def test_dont_cache_args(
        self, window, window_kwargs, nogil, parallel, nopython, method
    ):
        # GH 42287

        def add(values, x):
            return np.sum(values) + x

        engine_kwargs = {"nopython": nopython, "nogil": nogil, "parallel": parallel}
        df = DataFrame({"value": [0, 0, 0]})
        result = getattr(df, window)(method=method, **window_kwargs).apply(
            add, raw=True, engine="numba", engine_kwargs=engine_kwargs, args=(1,)
        )
        expected = DataFrame({"value": [1.0, 1.0, 1.0]})
        tm.assert_frame_equal(result, expected)

        result = getattr(df, window)(method=method, **window_kwargs).apply(
            add, raw=True, engine="numba", engine_kwargs=engine_kwargs, args=(2,)
        )
        expected = DataFrame({"value": [2.0, 2.0, 2.0]})
        tm.assert_frame_equal(result, expected)

    def test_dont_cache_engine_kwargs(self):
        # If the user passes a different set of engine_kwargs don't return the same
        # jitted function
        nogil = False
        parallel = True
        nopython = True

        def func(x):
            return nogil + parallel + nopython

        engine_kwargs = {"nopython": nopython, "nogil": nogil, "parallel": parallel}
        df = DataFrame({"value": [0, 0, 0]})
        result = df.rolling(1).apply(
            func, raw=True, engine="numba", engine_kwargs=engine_kwargs
        )
        expected = DataFrame({"value": [2.0, 2.0, 2.0]})
        tm.assert_frame_equal(result, expected)

        parallel = False
        engine_kwargs = {"nopython": nopython, "nogil": nogil, "parallel": parallel}
        result = df.rolling(1).apply(
            func, raw=True, engine="numba", engine_kwargs=engine_kwargs
        )
        expected = DataFrame({"value": [1.0, 1.0, 1.0]})
        tm.assert_frame_equal(result, expected)


@td.skip_if_no("numba")
class TestEWM:
    @pytest.mark.parametrize(
        "grouper", [lambda x: x, lambda x: x.groupby("A")], ids=["None", "groupby"]
    )
    @pytest.mark.parametrize("method", ["mean", "sum"])
    def test_invalid_engine(self, grouper, method):
        df = DataFrame({"A": ["a", "b", "a", "b"], "B": range(4)})
        with pytest.raises(ValueError, match="engine must be either"):
            getattr(grouper(df).ewm(com=1.0), method)(engine="foo")

    @pytest.mark.parametrize(
        "grouper", [lambda x: x, lambda x: x.groupby("A")], ids=["None", "groupby"]
    )
    @pytest.mark.parametrize("method", ["mean", "sum"])
    def test_invalid_engine_kwargs(self, grouper, method):
        df = DataFrame({"A": ["a", "b", "a", "b"], "B": range(4)})
        with pytest.raises(ValueError, match="cython engine does not"):
            getattr(grouper(df).ewm(com=1.0), method)(
                engine="cython", engine_kwargs={"nopython": True}
            )

    @pytest.mark.parametrize("grouper", ["None", "groupby"])
    @pytest.mark.parametrize("method", ["mean", "sum"])
    def test_cython_vs_numba(
        self, grouper, method, nogil, parallel, nopython, ignore_na, adjust
    ):
        df = DataFrame({"B": range(4)})
        if grouper == "None":
            grouper = lambda x: x
        else:
            df["A"] = ["a", "b", "a", "b"]
            grouper = lambda x: x.groupby("A")
        if method == "sum":
            adjust = True
        ewm = grouper(df).ewm(com=1.0, adjust=adjust, ignore_na=ignore_na)

        engine_kwargs = {"nogil": nogil, "parallel": parallel, "nopython": nopython}
        result = getattr(ewm, method)(engine="numba", engine_kwargs=engine_kwargs)
        expected = getattr(ewm, method)(engine="cython")

        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("grouper", ["None", "groupby"])
    def test_cython_vs_numba_times(self, grouper, nogil, parallel, nopython, ignore_na):
        # GH 40951

        df = DataFrame({"B": [0, 0, 1, 1, 2, 2]})
        if grouper == "None":
            grouper = lambda x: x
        else:
            grouper = lambda x: x.groupby("A")
            df["A"] = ["a", "b", "a", "b", "b", "a"]

        halflife = "23 days"
        times = to_datetime(
            [
                "2020-01-01",
                "2020-01-01",
                "2020-01-02",
                "2020-01-10",
                "2020-02-23",
                "2020-01-03",
            ]
        )
        ewm = grouper(df).ewm(
            halflife=halflife, adjust=True, ignore_na=ignore_na, times=times
        )

        engine_kwargs = {"nogil": nogil, "parallel": parallel, "nopython": nopython}

        result = ewm.mean(engine="numba", engine_kwargs=engine_kwargs)
        expected = ewm.mean(engine="cython")

        tm.assert_frame_equal(result, expected)


@td.skip_if_no("numba")
def test_use_global_config():
    def f(x):
        return np.mean(x) + 2

    s = Series(range(10))
    with option_context("compute.use_numba", True):
        result = s.rolling(2).apply(f, engine=None, raw=True)
    expected = s.rolling(2).apply(f, engine="numba", raw=True)
    tm.assert_series_equal(expected, result)


@td.skip_if_no("numba")
def test_invalid_kwargs_nopython():
    with pytest.raises(NumbaUtilError, match="numba does not support kwargs with"):
        Series(range(1)).rolling(1).apply(
            lambda x: x, kwargs={"a": 1}, engine="numba", raw=True
        )


@td.skip_if_no("numba")
@pytest.mark.slow
@pytest.mark.filterwarnings("ignore")
# Filter warnings when parallel=True and the function can't be parallelized by Numba
class TestTableMethod:
    def test_table_series_valueerror(self):
        def f(x):
            return np.sum(x, axis=0) + 1

        with pytest.raises(
            ValueError, match="method='table' not applicable for Series objects."
        ):
            Series(range(1)).rolling(1, method="table").apply(
                f, engine="numba", raw=True
            )

    def test_table_method_rolling_methods(
        self,
        axis,
        nogil,
        parallel,
        nopython,
        arithmetic_numba_supported_operators,
        step,
    ):
        method, kwargs = arithmetic_numba_supported_operators

        engine_kwargs = {"nogil": nogil, "parallel": parallel, "nopython": nopython}

        df = DataFrame(np.eye(3))
        roll_table = df.rolling(2, method="table", axis=axis, min_periods=0, step=step)
        if method in ("var", "std"):
            with pytest.raises(NotImplementedError, match=f"{method} not supported"):
                getattr(roll_table, method)(
                    engine_kwargs=engine_kwargs, engine="numba", **kwargs
                )
        else:
            roll_single = df.rolling(
                2, method="single", axis=axis, min_periods=0, step=step
            )
            result = getattr(roll_table, method)(
                engine_kwargs=engine_kwargs, engine="numba", **kwargs
            )
            expected = getattr(roll_single, method)(
                engine_kwargs=engine_kwargs, engine="numba", **kwargs
            )
            tm.assert_frame_equal(result, expected)

    def test_table_method_rolling_apply(self, axis, nogil, parallel, nopython, step):
        engine_kwargs = {"nogil": nogil, "parallel": parallel, "nopython": nopython}

        def f(x):
            return np.sum(x, axis=0) + 1

        df = DataFrame(np.eye(3))
        result = df.rolling(
            2, method="table", axis=axis, min_periods=0, step=step
        ).apply(f, raw=True, engine_kwargs=engine_kwargs, engine="numba")
        expected = df.rolling(
            2, method="single", axis=axis, min_periods=0, step=step
        ).apply(f, raw=True, engine_kwargs=engine_kwargs, engine="numba")
        tm.assert_frame_equal(result, expected)

    def test_table_method_rolling_weighted_mean(self, step):
        def weighted_mean(x):
            arr = np.ones((1, x.shape[1]))
            arr[:, :2] = (x[:, :2] * x[:, 2]).sum(axis=0) / x[:, 2].sum()
            return arr

        df = DataFrame([[1, 2, 0.6], [2, 3, 0.4], [3, 4, 0.2], [4, 5, 0.7]])
        result = df.rolling(2, method="table", min_periods=0, step=step).apply(
            weighted_mean, raw=True, engine="numba"
        )
        expected = DataFrame(
            [
                [1.0, 2.0, 1.0],
                [1.8, 2.0, 1.0],
                [3.333333, 2.333333, 1.0],
                [1.555556, 7, 1.0],
            ]
        )[::step]
        tm.assert_frame_equal(result, expected)

    def test_table_method_expanding_apply(self, axis, nogil, parallel, nopython):
        engine_kwargs = {"nogil": nogil, "parallel": parallel, "nopython": nopython}

        def f(x):
            return np.sum(x, axis=0) + 1

        df = DataFrame(np.eye(3))
        result = df.expanding(method="table", axis=axis).apply(
            f, raw=True, engine_kwargs=engine_kwargs, engine="numba"
        )
        expected = df.expanding(method="single", axis=axis).apply(
            f, raw=True, engine_kwargs=engine_kwargs, engine="numba"
        )
        tm.assert_frame_equal(result, expected)

    def test_table_method_expanding_methods(
        self, axis, nogil, parallel, nopython, arithmetic_numba_supported_operators
    ):
        method, kwargs = arithmetic_numba_supported_operators

        engine_kwargs = {"nogil": nogil, "parallel": parallel, "nopython": nopython}

        df = DataFrame(np.eye(3))
        expand_table = df.expanding(method="table", axis=axis)
        if method in ("var", "std"):
            with pytest.raises(NotImplementedError, match=f"{method} not supported"):
                getattr(expand_table, method)(
                    engine_kwargs=engine_kwargs, engine="numba", **kwargs
                )
        else:
            expand_single = df.expanding(method="single", axis=axis)
            result = getattr(expand_table, method)(
                engine_kwargs=engine_kwargs, engine="numba", **kwargs
            )
            expected = getattr(expand_single, method)(
                engine_kwargs=engine_kwargs, engine="numba", **kwargs
            )
            tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("data", [np.eye(3), np.ones((2, 3)), np.ones((3, 2))])
    @pytest.mark.parametrize("method", ["mean", "sum"])
    def test_table_method_ewm(self, data, method, axis, nogil, parallel, nopython):
        engine_kwargs = {"nogil": nogil, "parallel": parallel, "nopython": nopython}

        df = DataFrame(data)

        result = getattr(df.ewm(com=1, method="table", axis=axis), method)(
            engine_kwargs=engine_kwargs, engine="numba"
        )
        expected = getattr(df.ewm(com=1, method="single", axis=axis), method)(
            engine_kwargs=engine_kwargs, engine="numba"
        )
        tm.assert_frame_equal(result, expected)


@td.skip_if_no("numba")
def test_npfunc_no_warnings():
    df = DataFrame({"col1": [1, 2, 3, 4, 5]})
    with tm.assert_produces_warning(False):
        df.col1.rolling(2).apply(np.prod, raw=True, engine="numba")
