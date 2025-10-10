import re

import numpy as np
import pytest

from pandas._libs import lib

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    Series,
    Timestamp,
    date_range,
)
import pandas._testing as tm
from pandas.tests.groupby import get_groupby_method_args


class TestNumericOnly:
    # make sure that we are passing thru kwargs to our agg functions

    @pytest.fixture
    def df(self):
        # GH3668
        # GH5724
        df = DataFrame(
            {
                "group": [1, 1, 2],
                "int": [1, 2, 3],
                "float": [4.0, 5.0, 6.0],
                "string": Series(["a", "b", "c"], dtype="str"),
                "object": Series(["a", "b", "c"], dtype=object),
                "category_string": Series(list("abc")).astype("category"),
                "category_int": [7, 8, 9],
                "datetime": date_range("20130101", periods=3),
                "datetimetz": date_range("20130101", periods=3, tz="US/Eastern"),
                "timedelta": pd.timedelta_range("1 s", periods=3, freq="s"),
            },
            columns=[
                "group",
                "int",
                "float",
                "string",
                "object",
                "category_string",
                "category_int",
                "datetime",
                "datetimetz",
                "timedelta",
            ],
        )
        return df

    @pytest.mark.parametrize("method", ["mean", "median"])
    def test_averages(self, df, method):
        # mean / median
        expected_columns_numeric = Index(["int", "float", "category_int"])

        gb = df.groupby("group")
        expected = DataFrame(
            {
                "category_int": [7.5, 9],
                "float": [4.5, 6.0],
                "timedelta": [pd.Timedelta("1.5s"), pd.Timedelta("3s")],
                "int": [1.5, 3],
                "datetime": [
                    Timestamp("2013-01-01 12:00:00"),
                    Timestamp("2013-01-03 00:00:00"),
                ],
                "datetimetz": [
                    Timestamp("2013-01-01 12:00:00", tz="US/Eastern"),
                    Timestamp("2013-01-03 00:00:00", tz="US/Eastern"),
                ],
            },
            index=Index([1, 2], name="group"),
            columns=[
                "int",
                "float",
                "category_int",
            ],
        )

        result = getattr(gb, method)(numeric_only=True)
        tm.assert_frame_equal(result.reindex_like(expected), expected)

        expected_columns = expected.columns

        self._check(df, method, expected_columns, expected_columns_numeric)

    @pytest.mark.parametrize("method", ["min", "max"])
    def test_extrema(self, df, method):
        # TODO: min, max *should* handle
        # categorical (ordered) dtype

        expected_columns = Index(
            [
                "int",
                "float",
                "string",
                "category_int",
                "datetime",
                "datetimetz",
                "timedelta",
            ]
        )
        expected_columns_numeric = expected_columns

        self._check(df, method, expected_columns, expected_columns_numeric)

    @pytest.mark.parametrize("method", ["first", "last"])
    def test_first_last(self, df, method):
        expected_columns = Index(
            [
                "int",
                "float",
                "string",
                "object",
                "category_string",
                "category_int",
                "datetime",
                "datetimetz",
                "timedelta",
            ]
        )
        expected_columns_numeric = expected_columns

        self._check(df, method, expected_columns, expected_columns_numeric)

    @pytest.mark.parametrize("method", ["sum", "cumsum"])
    def test_sum_cumsum(self, df, method):
        expected_columns_numeric = Index(["int", "float", "category_int"])
        expected_columns = Index(
            ["int", "float", "string", "category_int", "timedelta"]
        )
        if method == "cumsum":
            # cumsum loses string
            expected_columns = Index(["int", "float", "category_int", "timedelta"])

        self._check(df, method, expected_columns, expected_columns_numeric)

    @pytest.mark.parametrize("method", ["prod", "cumprod"])
    def test_prod_cumprod(self, df, method):
        expected_columns = Index(["int", "float", "category_int"])
        expected_columns_numeric = expected_columns

        self._check(df, method, expected_columns, expected_columns_numeric)

    @pytest.mark.parametrize("method", ["cummin", "cummax"])
    def test_cummin_cummax(self, df, method):
        # like min, max, but don't include strings
        expected_columns = Index(
            ["int", "float", "category_int", "datetime", "datetimetz", "timedelta"]
        )

        # GH#15561: numeric_only=False set by default like min/max
        expected_columns_numeric = expected_columns

        self._check(df, method, expected_columns, expected_columns_numeric)

    def _check(self, df, method, expected_columns, expected_columns_numeric):
        gb = df.groupby("group")

        # object dtypes for transformations are not implemented in Cython and
        # have no Python fallback
        exception = (
            (NotImplementedError, TypeError) if method.startswith("cum") else TypeError
        )

        if method in ("min", "max", "cummin", "cummax", "cumsum", "cumprod"):
            # The methods default to numeric_only=False and raise TypeError
            msg = "|".join(
                [
                    "Categorical is not ordered",
                    f"Cannot perform {method} with non-ordered Categorical",
                    re.escape(f"agg function failed [how->{method},dtype->object]"),
                    # cumsum/cummin/cummax/cumprod
                    "function is not implemented for this dtype",
                    f"dtype 'str' does not support operation '{method}'",
                ]
            )
            with pytest.raises(exception, match=msg):
                getattr(gb, method)()
        elif method in ("sum", "mean", "median", "prod"):
            msg = "|".join(
                [
                    "category type does not support sum operations",
                    re.escape(f"agg function failed [how->{method},dtype->object]"),
                    re.escape(f"agg function failed [how->{method},dtype->string]"),
                    f"dtype 'str' does not support operation '{method}'",
                ]
            )
            with pytest.raises(exception, match=msg):
                getattr(gb, method)()
        else:
            result = getattr(gb, method)()
            tm.assert_index_equal(result.columns, expected_columns_numeric)

        if method not in ("first", "last"):
            msg = "|".join(
                [
                    "Categorical is not ordered",
                    "category type does not support",
                    "function is not implemented for this dtype",
                    f"Cannot perform {method} with non-ordered Categorical",
                    re.escape(f"agg function failed [how->{method},dtype->object]"),
                    re.escape(f"agg function failed [how->{method},dtype->string]"),
                    f"dtype 'str' does not support operation '{method}'",
                ]
            )
            with pytest.raises(exception, match=msg):
                getattr(gb, method)(numeric_only=False)
        else:
            result = getattr(gb, method)(numeric_only=False)
            tm.assert_index_equal(result.columns, expected_columns)


@pytest.mark.parametrize("numeric_only", [True, False, None])
def test_axis1_numeric_only(request, groupby_func, numeric_only, using_infer_string):
    if groupby_func in ("idxmax", "idxmin"):
        pytest.skip("idxmax and idx_min tested in test_idxmin_idxmax_axis1")
    if groupby_func in ("corrwith", "skew"):
        msg = "GH#47723 groupby.corrwith and skew do not correctly implement axis=1"
        request.applymarker(pytest.mark.xfail(reason=msg))

    df = DataFrame(
        np.random.default_rng(2).standard_normal((10, 4)), columns=["A", "B", "C", "D"]
    )
    df["E"] = "x"
    groups = [1, 2, 3, 1, 2, 3, 1, 2, 3, 4]
    gb = df.groupby(groups)
    method = getattr(gb, groupby_func)
    args = get_groupby_method_args(groupby_func, df)
    kwargs = {"axis": 1}
    if numeric_only is not None:
        # when numeric_only is None we don't pass any argument
        kwargs["numeric_only"] = numeric_only

    # Functions without numeric_only and axis args
    no_args = ("cumprod", "cumsum", "diff", "fillna", "pct_change", "rank", "shift")
    # Functions with axis args
    has_axis = (
        "cumprod",
        "cumsum",
        "diff",
        "pct_change",
        "rank",
        "shift",
        "cummax",
        "cummin",
        "idxmin",
        "idxmax",
        "fillna",
    )
    warn_msg = f"DataFrameGroupBy.{groupby_func} with axis=1 is deprecated"
    if numeric_only is not None and groupby_func in no_args:
        msg = "got an unexpected keyword argument 'numeric_only'"
        if groupby_func in ["cumprod", "cumsum"]:
            with pytest.raises(TypeError, match=msg):
                with tm.assert_produces_warning(FutureWarning, match=warn_msg):
                    method(*args, **kwargs)
        else:
            with pytest.raises(TypeError, match=msg):
                method(*args, **kwargs)
    elif groupby_func not in has_axis:
        msg = "got an unexpected keyword argument 'axis'"
        with pytest.raises(TypeError, match=msg):
            method(*args, **kwargs)
    # fillna and shift are successful even on object dtypes
    elif (numeric_only is None or not numeric_only) and groupby_func not in (
        "fillna",
        "shift",
    ):
        msgs = (
            # cummax, cummin, rank
            "not supported between instances of",
            # cumprod
            "can't multiply sequence by non-int of type 'float'",
            # cumsum, diff, pct_change
            "unsupported operand type",
            "has no kernel",
            "operation 'sub' not supported for dtype 'str' with dtype 'float64'",
        )
        if using_infer_string:
            pa = pytest.importorskip("pyarrow")

            errs = (TypeError, pa.lib.ArrowNotImplementedError)
        else:
            errs = TypeError
        with pytest.raises(errs, match=f"({'|'.join(msgs)})"):
            with tm.assert_produces_warning(FutureWarning, match=warn_msg):
                method(*args, **kwargs)
    else:
        with tm.assert_produces_warning(FutureWarning, match=warn_msg):
            result = method(*args, **kwargs)

        df_expected = df.drop(columns="E").T if numeric_only else df.T
        expected = getattr(df_expected, groupby_func)(*args).T
        if groupby_func == "shift" and not numeric_only:
            # shift with axis=1 leaves the leftmost column as numeric
            # but transposing for expected gives us object dtype
            expected = expected.astype(float)

        tm.assert_equal(result, expected)


@pytest.mark.parametrize(
    "kernel, has_arg",
    [
        ("all", False),
        ("any", False),
        ("bfill", False),
        ("corr", True),
        ("corrwith", True),
        ("cov", True),
        ("cummax", True),
        ("cummin", True),
        ("cumprod", True),
        ("cumsum", True),
        ("diff", False),
        ("ffill", False),
        ("fillna", False),
        ("first", True),
        ("idxmax", True),
        ("idxmin", True),
        ("last", True),
        ("max", True),
        ("mean", True),
        ("median", True),
        ("min", True),
        ("nth", False),
        ("nunique", False),
        ("pct_change", False),
        ("prod", True),
        ("quantile", True),
        ("sem", True),
        ("skew", True),
        ("std", True),
        ("sum", True),
        ("var", True),
    ],
)
@pytest.mark.parametrize("numeric_only", [True, False, lib.no_default])
@pytest.mark.parametrize("keys", [["a1"], ["a1", "a2"]])
def test_numeric_only(kernel, has_arg, numeric_only, keys):
    # GH#46072
    # drops_nuisance: Whether the op drops nuisance columns even when numeric_only=False
    # has_arg: Whether the op has a numeric_only arg
    df = DataFrame({"a1": [1, 1], "a2": [2, 2], "a3": [5, 6], "b": 2 * [object]})

    args = get_groupby_method_args(kernel, df)
    kwargs = {} if numeric_only is lib.no_default else {"numeric_only": numeric_only}

    gb = df.groupby(keys)
    method = getattr(gb, kernel)
    if has_arg and numeric_only is True:
        # Cases where b does not appear in the result
        result = method(*args, **kwargs)
        assert "b" not in result.columns
    elif (
        # kernels that work on any dtype and have numeric_only arg
        kernel in ("first", "last")
        or (
            # kernels that work on any dtype and don't have numeric_only arg
            kernel in ("any", "all", "bfill", "ffill", "fillna", "nth", "nunique")
            and numeric_only is lib.no_default
        )
    ):
        warn = FutureWarning if kernel == "fillna" else None
        msg = "DataFrameGroupBy.fillna is deprecated"
        with tm.assert_produces_warning(warn, match=msg):
            result = method(*args, **kwargs)
        assert "b" in result.columns
    elif has_arg:
        assert numeric_only is not True
        # kernels that are successful on any dtype were above; this will fail

        # object dtypes for transformations are not implemented in Cython and
        # have no Python fallback
        exception = NotImplementedError if kernel.startswith("cum") else TypeError

        msg = "|".join(
            [
                "not allowed for this dtype",
                "cannot be performed against 'object' dtypes",
                # On PY39 message is "a number"; on PY310 and after is "a real number"
                "must be a string or a.* number",
                "unsupported operand type",
                "function is not implemented for this dtype",
                re.escape(f"agg function failed [how->{kernel},dtype->object]"),
            ]
        )
        if kernel == "quantile":
            msg = "dtype 'object' does not support operation 'quantile'"
        elif kernel == "idxmin":
            msg = "'<' not supported between instances of 'type' and 'type'"
        elif kernel == "idxmax":
            msg = "'>' not supported between instances of 'type' and 'type'"
        with pytest.raises(exception, match=msg):
            method(*args, **kwargs)
    elif not has_arg and numeric_only is not lib.no_default:
        with pytest.raises(
            TypeError, match="got an unexpected keyword argument 'numeric_only'"
        ):
            method(*args, **kwargs)
    else:
        assert kernel in ("diff", "pct_change")
        assert numeric_only is lib.no_default
        # Doesn't have numeric_only argument and fails on nuisance columns
        with pytest.raises(TypeError, match=r"unsupported operand type"):
            method(*args, **kwargs)


@pytest.mark.filterwarnings("ignore:Downcasting object dtype arrays:FutureWarning")
@pytest.mark.parametrize("dtype", [bool, int, float, object])
def test_deprecate_numeric_only_series(dtype, groupby_func, request):
    # GH#46560
    grouper = [0, 0, 1]

    ser = Series([1, 0, 0], dtype=dtype)
    gb = ser.groupby(grouper)

    if groupby_func == "corrwith":
        # corrwith is not implemented on SeriesGroupBy
        assert not hasattr(gb, groupby_func)
        return

    method = getattr(gb, groupby_func)

    expected_ser = Series([1, 0, 0])
    expected_gb = expected_ser.groupby(grouper)
    expected_method = getattr(expected_gb, groupby_func)

    args = get_groupby_method_args(groupby_func, ser)

    fails_on_numeric_object = (
        "corr",
        "cov",
        "cummax",
        "cummin",
        "cumprod",
        "cumsum",
        "quantile",
    )
    # ops that give an object result on object input
    obj_result = (
        "first",
        "last",
        "nth",
        "bfill",
        "ffill",
        "shift",
        "sum",
        "diff",
        "pct_change",
        "var",
        "mean",
        "median",
        "min",
        "max",
        "prod",
        "skew",
    )

    # Test default behavior; kernels that fail may be enabled in the future but kernels
    # that succeed should not be allowed to fail (without deprecation, at least)
    if groupby_func in fails_on_numeric_object and dtype is object:
        if groupby_func == "quantile":
            msg = "dtype 'object' does not support operation 'quantile'"
        else:
            msg = "is not supported for object dtype"
        warn = FutureWarning if groupby_func == "fillna" else None
        warn_msg = "DataFrameGroupBy.fillna is deprecated"
        with tm.assert_produces_warning(warn, match=warn_msg):
            with pytest.raises(TypeError, match=msg):
                method(*args)
    elif dtype is object:
        warn = FutureWarning if groupby_func == "fillna" else None
        warn_msg = "SeriesGroupBy.fillna is deprecated"
        with tm.assert_produces_warning(warn, match=warn_msg):
            result = method(*args)
        with tm.assert_produces_warning(warn, match=warn_msg):
            expected = expected_method(*args)
        if groupby_func in obj_result:
            expected = expected.astype(object)
        tm.assert_series_equal(result, expected)

    has_numeric_only = (
        "first",
        "last",
        "max",
        "mean",
        "median",
        "min",
        "prod",
        "quantile",
        "sem",
        "skew",
        "std",
        "sum",
        "var",
        "cummax",
        "cummin",
        "cumprod",
        "cumsum",
    )
    if groupby_func not in has_numeric_only:
        msg = "got an unexpected keyword argument 'numeric_only'"
        with pytest.raises(TypeError, match=msg):
            method(*args, numeric_only=True)
    elif dtype is object:
        msg = "|".join(
            [
                "SeriesGroupBy.sem called with numeric_only=True and dtype object",
                "Series.skew does not allow numeric_only=True with non-numeric",
                "cum(sum|prod|min|max) is not supported for object dtype",
                r"Cannot use numeric_only=True with SeriesGroupBy\..* and non-numeric",
            ]
        )
        with pytest.raises(TypeError, match=msg):
            method(*args, numeric_only=True)
    elif dtype == bool and groupby_func == "quantile":
        msg = "Allowing bool dtype in SeriesGroupBy.quantile"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            # GH#51424
            result = method(*args, numeric_only=True)
            expected = method(*args, numeric_only=False)
        tm.assert_series_equal(result, expected)
    else:
        result = method(*args, numeric_only=True)
        expected = method(*args, numeric_only=False)
        tm.assert_series_equal(result, expected)
