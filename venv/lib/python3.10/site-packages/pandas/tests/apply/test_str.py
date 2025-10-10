from itertools import chain
import operator

import numpy as np
import pytest

from pandas.core.dtypes.common import is_number

from pandas import (
    DataFrame,
    Series,
)
import pandas._testing as tm
from pandas.tests.apply.common import (
    frame_transform_kernels,
    series_transform_kernels,
)


@pytest.mark.parametrize("func", ["sum", "mean", "min", "max", "std"])
@pytest.mark.parametrize(
    "args,kwds",
    [
        pytest.param([], {}, id="no_args_or_kwds"),
        pytest.param([1], {}, id="axis_from_args"),
        pytest.param([], {"axis": 1}, id="axis_from_kwds"),
        pytest.param([], {"numeric_only": True}, id="optional_kwds"),
        pytest.param([1, True], {"numeric_only": True}, id="args_and_kwds"),
    ],
)
@pytest.mark.parametrize("how", ["agg", "apply"])
def test_apply_with_string_funcs(request, float_frame, func, args, kwds, how):
    if len(args) > 1 and how == "agg":
        request.applymarker(
            pytest.mark.xfail(
                raises=TypeError,
                reason="agg/apply signature mismatch - agg passes 2nd "
                "argument to func",
            )
        )
    result = getattr(float_frame, how)(func, *args, **kwds)
    expected = getattr(float_frame, func)(*args, **kwds)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("arg", ["sum", "mean", "min", "max", "std"])
def test_with_string_args(datetime_series, arg):
    result = datetime_series.apply(arg)
    expected = getattr(datetime_series, arg)()
    assert result == expected


@pytest.mark.parametrize("op", ["mean", "median", "std", "var"])
@pytest.mark.parametrize("how", ["agg", "apply"])
def test_apply_np_reducer(op, how):
    # GH 39116
    float_frame = DataFrame({"a": [1, 2], "b": [3, 4]})
    result = getattr(float_frame, how)(op)
    # pandas ddof defaults to 1, numpy to 0
    kwargs = {"ddof": 1} if op in ("std", "var") else {}
    expected = Series(
        getattr(np, op)(float_frame, axis=0, **kwargs), index=float_frame.columns
    )
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "op", ["abs", "ceil", "cos", "cumsum", "exp", "log", "sqrt", "square"]
)
@pytest.mark.parametrize("how", ["transform", "apply"])
def test_apply_np_transformer(float_frame, op, how):
    # GH 39116

    # float_frame will _usually_ have negative values, which will
    #  trigger the warning here, but let's put one in just to be sure
    float_frame.iloc[0, 0] = -1.0
    warn = None
    if op in ["log", "sqrt"]:
        warn = RuntimeWarning

    with tm.assert_produces_warning(warn, check_stacklevel=False):
        # float_frame fixture is defined in conftest.py, so we don't check the
        # stacklevel as otherwise the test would fail.
        result = getattr(float_frame, how)(op)
        expected = getattr(np, op)(float_frame)
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "series, func, expected",
    chain(
        tm.get_cython_table_params(
            Series(dtype=np.float64),
            [
                ("sum", 0),
                ("max", np.nan),
                ("min", np.nan),
                ("all", True),
                ("any", False),
                ("mean", np.nan),
                ("prod", 1),
                ("std", np.nan),
                ("var", np.nan),
                ("median", np.nan),
            ],
        ),
        tm.get_cython_table_params(
            Series([np.nan, 1, 2, 3]),
            [
                ("sum", 6),
                ("max", 3),
                ("min", 1),
                ("all", True),
                ("any", True),
                ("mean", 2),
                ("prod", 6),
                ("std", 1),
                ("var", 1),
                ("median", 2),
            ],
        ),
        tm.get_cython_table_params(
            Series("a b c".split()),
            [
                ("sum", "abc"),
                ("max", "c"),
                ("min", "a"),
                ("all", True),
                ("any", True),
            ],
        ),
    ),
)
def test_agg_cython_table_series(series, func, expected):
    # GH21224
    # test reducing functions in
    # pandas.core.base.SelectionMixin._cython_table
    warn = None if isinstance(func, str) else FutureWarning
    with tm.assert_produces_warning(warn, match="is currently using Series.*"):
        result = series.agg(func)
    if is_number(expected):
        assert np.isclose(result, expected, equal_nan=True)
    else:
        assert result == expected


@pytest.mark.parametrize(
    "series, func, expected",
    chain(
        tm.get_cython_table_params(
            Series(dtype=np.float64),
            [
                ("cumprod", Series([], dtype=np.float64)),
                ("cumsum", Series([], dtype=np.float64)),
            ],
        ),
        tm.get_cython_table_params(
            Series([np.nan, 1, 2, 3]),
            [
                ("cumprod", Series([np.nan, 1, 2, 6])),
                ("cumsum", Series([np.nan, 1, 3, 6])),
            ],
        ),
        tm.get_cython_table_params(
            Series("a b c".split()), [("cumsum", Series(["a", "ab", "abc"]))]
        ),
    ),
)
def test_agg_cython_table_transform_series(series, func, expected):
    # GH21224
    # test transforming functions in
    # pandas.core.base.SelectionMixin._cython_table (cumprod, cumsum)
    warn = None if isinstance(func, str) else FutureWarning
    with tm.assert_produces_warning(warn, match="is currently using Series.*"):
        result = series.agg(func)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "df, func, expected",
    chain(
        tm.get_cython_table_params(
            DataFrame(),
            [
                ("sum", Series(dtype="float64")),
                ("max", Series(dtype="float64")),
                ("min", Series(dtype="float64")),
                ("all", Series(dtype=bool)),
                ("any", Series(dtype=bool)),
                ("mean", Series(dtype="float64")),
                ("prod", Series(dtype="float64")),
                ("std", Series(dtype="float64")),
                ("var", Series(dtype="float64")),
                ("median", Series(dtype="float64")),
            ],
        ),
        tm.get_cython_table_params(
            DataFrame([[np.nan, 1], [1, 2]]),
            [
                ("sum", Series([1.0, 3])),
                ("max", Series([1.0, 2])),
                ("min", Series([1.0, 1])),
                ("all", Series([True, True])),
                ("any", Series([True, True])),
                ("mean", Series([1, 1.5])),
                ("prod", Series([1.0, 2])),
                ("std", Series([np.nan, 0.707107])),
                ("var", Series([np.nan, 0.5])),
                ("median", Series([1, 1.5])),
            ],
        ),
    ),
)
def test_agg_cython_table_frame(df, func, expected, axis):
    # GH 21224
    # test reducing functions in
    # pandas.core.base.SelectionMixin._cython_table
    warn = None if isinstance(func, str) else FutureWarning
    with tm.assert_produces_warning(warn, match="is currently using DataFrame.*"):
        # GH#53425
        result = df.agg(func, axis=axis)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "df, func, expected",
    chain(
        tm.get_cython_table_params(
            DataFrame(), [("cumprod", DataFrame()), ("cumsum", DataFrame())]
        ),
        tm.get_cython_table_params(
            DataFrame([[np.nan, 1], [1, 2]]),
            [
                ("cumprod", DataFrame([[np.nan, 1], [1, 2]])),
                ("cumsum", DataFrame([[np.nan, 1], [1, 3]])),
            ],
        ),
    ),
)
def test_agg_cython_table_transform_frame(df, func, expected, axis):
    # GH 21224
    # test transforming functions in
    # pandas.core.base.SelectionMixin._cython_table (cumprod, cumsum)
    if axis in ("columns", 1):
        # operating blockwise doesn't let us preserve dtypes
        expected = expected.astype("float64")

    warn = None if isinstance(func, str) else FutureWarning
    with tm.assert_produces_warning(warn, match="is currently using DataFrame.*"):
        # GH#53425
        result = df.agg(func, axis=axis)
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("op", series_transform_kernels)
def test_transform_groupby_kernel_series(request, string_series, op):
    # GH 35964
    if op == "ngroup":
        request.applymarker(
            pytest.mark.xfail(raises=ValueError, reason="ngroup not valid for NDFrame")
        )
    args = [0.0] if op == "fillna" else []
    ones = np.ones(string_series.shape[0])

    warn = FutureWarning if op == "fillna" else None
    msg = "SeriesGroupBy.fillna is deprecated"
    with tm.assert_produces_warning(warn, match=msg):
        expected = string_series.groupby(ones).transform(op, *args)
    result = string_series.transform(op, 0, *args)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("op", frame_transform_kernels)
def test_transform_groupby_kernel_frame(request, axis, float_frame, op):
    if op == "ngroup":
        request.applymarker(
            pytest.mark.xfail(raises=ValueError, reason="ngroup not valid for NDFrame")
        )

    # GH 35964

    args = [0.0] if op == "fillna" else []
    if axis in (0, "index"):
        ones = np.ones(float_frame.shape[0])
        msg = "The 'axis' keyword in DataFrame.groupby is deprecated"
    else:
        ones = np.ones(float_frame.shape[1])
        msg = "DataFrame.groupby with axis=1 is deprecated"

    with tm.assert_produces_warning(FutureWarning, match=msg):
        gb = float_frame.groupby(ones, axis=axis)

    warn = FutureWarning if op == "fillna" else None
    op_msg = "DataFrameGroupBy.fillna is deprecated"
    with tm.assert_produces_warning(warn, match=op_msg):
        expected = gb.transform(op, *args)

    result = float_frame.transform(op, axis, *args)
    tm.assert_frame_equal(result, expected)

    # same thing, but ensuring we have multiple blocks
    assert "E" not in float_frame.columns
    float_frame["E"] = float_frame["A"].copy()
    assert len(float_frame._mgr.arrays) > 1

    if axis in (0, "index"):
        ones = np.ones(float_frame.shape[0])
    else:
        ones = np.ones(float_frame.shape[1])
    with tm.assert_produces_warning(FutureWarning, match=msg):
        gb2 = float_frame.groupby(ones, axis=axis)
    warn = FutureWarning if op == "fillna" else None
    op_msg = "DataFrameGroupBy.fillna is deprecated"
    with tm.assert_produces_warning(warn, match=op_msg):
        expected2 = gb2.transform(op, *args)
    result2 = float_frame.transform(op, axis, *args)
    tm.assert_frame_equal(result2, expected2)


@pytest.mark.parametrize("method", ["abs", "shift", "pct_change", "cumsum", "rank"])
def test_transform_method_name(method):
    # GH 19760
    df = DataFrame({"A": [-1, 2]})
    result = df.transform(method)
    expected = operator.methodcaller(method)(df)
    tm.assert_frame_equal(result, expected)
