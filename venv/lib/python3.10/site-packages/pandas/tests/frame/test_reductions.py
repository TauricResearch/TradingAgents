from datetime import timedelta
from decimal import Decimal
import re

from dateutil.tz import tzlocal
import numpy as np
import pytest

from pandas.compat import (
    IS64,
    is_platform_windows,
)
from pandas.compat.numpy import np_version_gt2
import pandas.util._test_decorators as td

import pandas as pd
from pandas import (
    Categorical,
    CategoricalDtype,
    DataFrame,
    DatetimeIndex,
    Index,
    PeriodIndex,
    RangeIndex,
    Series,
    Timestamp,
    date_range,
    isna,
    notna,
    to_datetime,
    to_timedelta,
)
import pandas._testing as tm
from pandas.core import (
    algorithms,
    nanops,
)

is_windows_np2_or_is32 = (is_platform_windows() and not np_version_gt2) or not IS64
is_windows_or_is32 = is_platform_windows() or not IS64


def make_skipna_wrapper(alternative, skipna_alternative=None):
    """
    Create a function for calling on an array.

    Parameters
    ----------
    alternative : function
        The function to be called on the array with no NaNs.
        Only used when 'skipna_alternative' is None.
    skipna_alternative : function
        The function to be called on the original array

    Returns
    -------
    function
    """
    if skipna_alternative:

        def skipna_wrapper(x):
            return skipna_alternative(x.values)

    else:

        def skipna_wrapper(x):
            nona = x.dropna()
            if len(nona) == 0:
                return np.nan
            return alternative(nona)

    return skipna_wrapper


def assert_stat_op_calc(
    opname,
    alternative,
    frame,
    has_skipna=True,
    check_dtype=True,
    check_dates=False,
    rtol=1e-5,
    atol=1e-8,
    skipna_alternative=None,
):
    """
    Check that operator opname works as advertised on frame

    Parameters
    ----------
    opname : str
        Name of the operator to test on frame
    alternative : function
        Function that opname is tested against; i.e. "frame.opname()" should
        equal "alternative(frame)".
    frame : DataFrame
        The object that the tests are executed on
    has_skipna : bool, default True
        Whether the method "opname" has the kwarg "skip_na"
    check_dtype : bool, default True
        Whether the dtypes of the result of "frame.opname()" and
        "alternative(frame)" should be checked.
    check_dates : bool, default false
        Whether opname should be tested on a Datetime Series
    rtol : float, default 1e-5
        Relative tolerance.
    atol : float, default 1e-8
        Absolute tolerance.
    skipna_alternative : function, default None
        NaN-safe version of alternative
    """
    f = getattr(frame, opname)

    if check_dates:
        df = DataFrame({"b": date_range("1/1/2001", periods=2)})
        with tm.assert_produces_warning(None):
            result = getattr(df, opname)()
        assert isinstance(result, Series)

        df["a"] = range(len(df))
        with tm.assert_produces_warning(None):
            result = getattr(df, opname)()
        assert isinstance(result, Series)
        assert len(result)

    if has_skipna:

        def wrapper(x):
            return alternative(x.values)

        skipna_wrapper = make_skipna_wrapper(alternative, skipna_alternative)
        result0 = f(axis=0, skipna=False)
        result1 = f(axis=1, skipna=False)
        tm.assert_series_equal(
            result0, frame.apply(wrapper), check_dtype=check_dtype, rtol=rtol, atol=atol
        )
        tm.assert_series_equal(
            result1,
            frame.apply(wrapper, axis=1),
            rtol=rtol,
            atol=atol,
        )
    else:
        skipna_wrapper = alternative

    result0 = f(axis=0)
    result1 = f(axis=1)
    tm.assert_series_equal(
        result0,
        frame.apply(skipna_wrapper),
        check_dtype=check_dtype,
        rtol=rtol,
        atol=atol,
    )

    if opname in ["sum", "prod"]:
        expected = frame.apply(skipna_wrapper, axis=1)
        tm.assert_series_equal(
            result1, expected, check_dtype=False, rtol=rtol, atol=atol
        )

    # check dtypes
    if check_dtype:
        lcd_dtype = frame.values.dtype
        assert lcd_dtype == result0.dtype
        assert lcd_dtype == result1.dtype

    # bad axis
    with pytest.raises(ValueError, match="No axis named 2"):
        f(axis=2)

    # all NA case
    if has_skipna:
        all_na = frame * np.nan
        r0 = getattr(all_na, opname)(axis=0)
        r1 = getattr(all_na, opname)(axis=1)
        if opname in ["sum", "prod"]:
            unit = 1 if opname == "prod" else 0  # result for empty sum/prod
            expected = Series(unit, index=r0.index, dtype=r0.dtype)
            tm.assert_series_equal(r0, expected)
            expected = Series(unit, index=r1.index, dtype=r1.dtype)
            tm.assert_series_equal(r1, expected)


@pytest.fixture
def bool_frame_with_na():
    """
    Fixture for DataFrame of booleans with index of unique strings

    Columns are ['A', 'B', 'C', 'D']; some entries are missing
    """
    df = DataFrame(
        np.concatenate(
            [np.ones((15, 4), dtype=bool), np.zeros((15, 4), dtype=bool)], axis=0
        ),
        index=Index([f"foo_{i}" for i in range(30)], dtype=object),
        columns=Index(list("ABCD"), dtype=object),
        dtype=object,
    )
    # set some NAs
    df.iloc[5:10] = np.nan
    df.iloc[15:20, -2:] = np.nan
    return df


@pytest.fixture
def float_frame_with_na():
    """
    Fixture for DataFrame of floats with index of unique strings

    Columns are ['A', 'B', 'C', 'D']; some entries are missing
    """
    df = DataFrame(
        np.random.default_rng(2).standard_normal((30, 4)),
        index=Index([f"foo_{i}" for i in range(30)], dtype=object),
        columns=Index(list("ABCD"), dtype=object),
    )
    # set some NAs
    df.iloc[5:10] = np.nan
    df.iloc[15:20, -2:] = np.nan
    return df


class TestDataFrameAnalytics:
    # ---------------------------------------------------------------------
    # Reductions
    @pytest.mark.parametrize("axis", [0, 1])
    @pytest.mark.parametrize(
        "opname",
        [
            "count",
            "sum",
            "mean",
            "product",
            "median",
            "min",
            "max",
            "nunique",
            "var",
            "std",
            "sem",
            pytest.param("skew", marks=td.skip_if_no("scipy")),
            pytest.param("kurt", marks=td.skip_if_no("scipy")),
        ],
    )
    def test_stat_op_api_float_string_frame(self, float_string_frame, axis, opname):
        if (opname in ("sum", "min", "max") and axis == 0) or opname in (
            "count",
            "nunique",
        ):
            getattr(float_string_frame, opname)(axis=axis)
        else:
            if opname in ["var", "std", "sem", "skew", "kurt"]:
                msg = "could not convert string to float: 'bar'"
            elif opname == "product":
                if axis == 1:
                    msg = "can't multiply sequence by non-int of type 'float'"
                else:
                    msg = "can't multiply sequence by non-int of type 'str'"
            elif opname == "sum":
                msg = r"unsupported operand type\(s\) for \+: 'float' and 'str'"
            elif opname == "mean":
                if axis == 0:
                    # different message on different builds
                    msg = "|".join(
                        [
                            r"Could not convert \['.*'\] to numeric",
                            "Could not convert string '(bar){30}' to numeric",
                        ]
                    )
                else:
                    msg = r"unsupported operand type\(s\) for \+: 'float' and 'str'"
            elif opname in ["min", "max"]:
                msg = "'[><]=' not supported between instances of 'float' and 'str'"
            elif opname == "median":
                msg = re.compile(
                    r"Cannot convert \[.*\] to numeric|does not support|Cannot perform",
                    flags=re.S,
                )
            if not isinstance(msg, re.Pattern):
                msg = msg + "|does not support|Cannot perform reduction"
            with pytest.raises(TypeError, match=msg):
                getattr(float_string_frame, opname)(axis=axis)
        if opname != "nunique":
            getattr(float_string_frame, opname)(axis=axis, numeric_only=True)

    @pytest.mark.parametrize("axis", [0, 1])
    @pytest.mark.parametrize(
        "opname",
        [
            "count",
            "sum",
            "mean",
            "product",
            "median",
            "min",
            "max",
            "var",
            "std",
            "sem",
            pytest.param("skew", marks=td.skip_if_no("scipy")),
            pytest.param("kurt", marks=td.skip_if_no("scipy")),
        ],
    )
    def test_stat_op_api_float_frame(self, float_frame, axis, opname):
        getattr(float_frame, opname)(axis=axis, numeric_only=False)

    def test_stat_op_calc(self, float_frame_with_na, mixed_float_frame):
        def count(s):
            return notna(s).sum()

        def nunique(s):
            return len(algorithms.unique1d(s.dropna()))

        def var(x):
            return np.var(x, ddof=1)

        def std(x):
            return np.std(x, ddof=1)

        def sem(x):
            return np.std(x, ddof=1) / np.sqrt(len(x))

        assert_stat_op_calc(
            "nunique",
            nunique,
            float_frame_with_na,
            has_skipna=False,
            check_dtype=False,
            check_dates=True,
        )

        # GH#32571: rol needed for flaky CI builds
        # mixed types (with upcasting happening)
        assert_stat_op_calc(
            "sum",
            np.sum,
            mixed_float_frame.astype("float32"),
            check_dtype=False,
            rtol=1e-3,
        )

        assert_stat_op_calc(
            "sum", np.sum, float_frame_with_na, skipna_alternative=np.nansum
        )
        assert_stat_op_calc("mean", np.mean, float_frame_with_na, check_dates=True)
        assert_stat_op_calc(
            "product", np.prod, float_frame_with_na, skipna_alternative=np.nanprod
        )

        assert_stat_op_calc("var", var, float_frame_with_na)
        assert_stat_op_calc("std", std, float_frame_with_na)
        assert_stat_op_calc("sem", sem, float_frame_with_na)

        assert_stat_op_calc(
            "count",
            count,
            float_frame_with_na,
            has_skipna=False,
            check_dtype=False,
            check_dates=True,
        )

    def test_stat_op_calc_skew_kurtosis(self, float_frame_with_na):
        sp_stats = pytest.importorskip("scipy.stats")

        def skewness(x):
            if len(x) < 3:
                return np.nan
            return sp_stats.skew(x, bias=False)

        def kurt(x):
            if len(x) < 4:
                return np.nan
            return sp_stats.kurtosis(x, bias=False)

        assert_stat_op_calc("skew", skewness, float_frame_with_na)
        assert_stat_op_calc("kurt", kurt, float_frame_with_na)

    def test_median(self, float_frame_with_na, int_frame):
        def wrapper(x):
            if isna(x).any():
                return np.nan
            return np.median(x)

        assert_stat_op_calc("median", wrapper, float_frame_with_na, check_dates=True)
        assert_stat_op_calc(
            "median", wrapper, int_frame, check_dtype=False, check_dates=True
        )

    @pytest.mark.parametrize(
        "method", ["sum", "mean", "prod", "var", "std", "skew", "min", "max"]
    )
    @pytest.mark.parametrize(
        "df",
        [
            DataFrame(
                {
                    "a": [
                        -0.00049987540199591344,
                        -0.0016467257772919831,
                        0.00067695870775883013,
                    ],
                    "b": [-0, -0, 0.0],
                    "c": [
                        0.00031111847529610595,
                        0.0014902627951905339,
                        -0.00094099200035979691,
                    ],
                },
                index=["foo", "bar", "baz"],
                dtype="O",
            ),
            DataFrame({0: [np.nan, 2], 1: [np.nan, 3], 2: [np.nan, 4]}, dtype=object),
        ],
    )
    @pytest.mark.filterwarnings("ignore:Mismatched null-like values:FutureWarning")
    def test_stat_operators_attempt_obj_array(self, method, df, axis):
        # GH#676
        assert df.values.dtype == np.object_
        result = getattr(df, method)(axis=axis)
        expected = getattr(df.astype("f8"), method)(axis=axis).astype(object)
        if axis in [1, "columns"] and method in ["min", "max"]:
            expected[expected.isna()] = None
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("op", ["mean", "std", "var", "skew", "kurt", "sem"])
    def test_mixed_ops(self, op):
        # GH#16116
        df = DataFrame(
            {
                "int": [1, 2, 3, 4],
                "float": [1.0, 2.0, 3.0, 4.0],
                "str": ["a", "b", "c", "d"],
            }
        )
        msg = "|".join(
            [
                "Could not convert",
                "could not convert",
                "can't multiply sequence by non-int",
                "does not support",
                "Cannot perform",
            ]
        )
        with pytest.raises(TypeError, match=msg):
            getattr(df, op)()

        with pd.option_context("use_bottleneck", False):
            with pytest.raises(TypeError, match=msg):
                getattr(df, op)()

    def test_reduce_mixed_frame(self):
        # GH 6806
        df = DataFrame(
            {
                "bool_data": [True, True, False, False, False],
                "int_data": [10, 20, 30, 40, 50],
                "string_data": ["a", "b", "c", "d", "e"],
            }
        )
        df.reindex(columns=["bool_data", "int_data", "string_data"])
        test = df.sum(axis=0)
        tm.assert_numpy_array_equal(
            test.values, np.array([2, 150, "abcde"], dtype=object)
        )
        alt = df.T.sum(axis=1)
        tm.assert_series_equal(test, alt)

    def test_nunique(self):
        df = DataFrame({"A": [1, 1, 1], "B": [1, 2, 3], "C": [1, np.nan, 3]})
        tm.assert_series_equal(df.nunique(), Series({"A": 1, "B": 3, "C": 2}))
        tm.assert_series_equal(
            df.nunique(dropna=False), Series({"A": 1, "B": 3, "C": 3})
        )
        tm.assert_series_equal(df.nunique(axis=1), Series({0: 1, 1: 2, 2: 2}))
        tm.assert_series_equal(
            df.nunique(axis=1, dropna=False), Series({0: 1, 1: 3, 2: 2})
        )

    @pytest.mark.parametrize("tz", [None, "UTC"])
    def test_mean_mixed_datetime_numeric(self, tz):
        # https://github.com/pandas-dev/pandas/issues/24752
        df = DataFrame({"A": [1, 1], "B": [Timestamp("2000", tz=tz)] * 2})
        result = df.mean()
        expected = Series([1.0, Timestamp("2000", tz=tz)], index=["A", "B"])
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("tz", [None, "UTC"])
    def test_mean_includes_datetimes(self, tz):
        # https://github.com/pandas-dev/pandas/issues/24752
        # Behavior in 0.24.0rc1 was buggy.
        # As of 2.0 with numeric_only=None we do *not* drop datetime columns
        df = DataFrame({"A": [Timestamp("2000", tz=tz)] * 2})
        result = df.mean()

        expected = Series([Timestamp("2000", tz=tz)], index=["A"])
        tm.assert_series_equal(result, expected)

    def test_mean_mixed_string_decimal(self):
        # GH 11670
        # possible bug when calculating mean of DataFrame?

        d = [
            {"A": 2, "B": None, "C": Decimal("628.00")},
            {"A": 1, "B": None, "C": Decimal("383.00")},
            {"A": 3, "B": None, "C": Decimal("651.00")},
            {"A": 2, "B": None, "C": Decimal("575.00")},
            {"A": 4, "B": None, "C": Decimal("1114.00")},
            {"A": 1, "B": "TEST", "C": Decimal("241.00")},
            {"A": 2, "B": None, "C": Decimal("572.00")},
            {"A": 4, "B": None, "C": Decimal("609.00")},
            {"A": 3, "B": None, "C": Decimal("820.00")},
            {"A": 5, "B": None, "C": Decimal("1223.00")},
        ]

        df = DataFrame(d)

        with pytest.raises(
            TypeError, match="unsupported operand type|does not support|Cannot perform"
        ):
            df.mean()
        result = df[["A", "C"]].mean()
        expected = Series([2.7, 681.6], index=["A", "C"], dtype=object)
        tm.assert_series_equal(result, expected)

    def test_var_std(self, datetime_frame):
        result = datetime_frame.std(ddof=4)
        expected = datetime_frame.apply(lambda x: x.std(ddof=4))
        tm.assert_almost_equal(result, expected)

        result = datetime_frame.var(ddof=4)
        expected = datetime_frame.apply(lambda x: x.var(ddof=4))
        tm.assert_almost_equal(result, expected)

        arr = np.repeat(np.random.default_rng(2).random((1, 1000)), 1000, 0)
        result = nanops.nanvar(arr, axis=0)
        assert not (result < 0).any()

        with pd.option_context("use_bottleneck", False):
            result = nanops.nanvar(arr, axis=0)
            assert not (result < 0).any()

    @pytest.mark.parametrize("meth", ["sem", "var", "std"])
    def test_numeric_only_flag(self, meth):
        # GH 9201
        df1 = DataFrame(
            np.random.default_rng(2).standard_normal((5, 3)),
            columns=["foo", "bar", "baz"],
        )
        # Cast to object to avoid implicit cast when setting entry to "100" below
        df1 = df1.astype({"foo": object})
        # set one entry to a number in str format
        df1.loc[0, "foo"] = "100"

        df2 = DataFrame(
            np.random.default_rng(2).standard_normal((5, 3)),
            columns=["foo", "bar", "baz"],
        )
        # Cast to object to avoid implicit cast when setting entry to "a" below
        df2 = df2.astype({"foo": object})
        # set one entry to a non-number str
        df2.loc[0, "foo"] = "a"

        result = getattr(df1, meth)(axis=1, numeric_only=True)
        expected = getattr(df1[["bar", "baz"]], meth)(axis=1)
        tm.assert_series_equal(expected, result)

        result = getattr(df2, meth)(axis=1, numeric_only=True)
        expected = getattr(df2[["bar", "baz"]], meth)(axis=1)
        tm.assert_series_equal(expected, result)

        # df1 has all numbers, df2 has a letter inside
        msg = r"unsupported operand type\(s\) for -: 'float' and 'str'"
        with pytest.raises(TypeError, match=msg):
            getattr(df1, meth)(axis=1, numeric_only=False)
        msg = "could not convert string to float: 'a'"
        with pytest.raises(TypeError, match=msg):
            getattr(df2, meth)(axis=1, numeric_only=False)

    def test_sem(self, datetime_frame):
        result = datetime_frame.sem(ddof=4)
        expected = datetime_frame.apply(lambda x: x.std(ddof=4) / np.sqrt(len(x)))
        tm.assert_almost_equal(result, expected)

        arr = np.repeat(np.random.default_rng(2).random((1, 1000)), 1000, 0)
        result = nanops.nansem(arr, axis=0)
        assert not (result < 0).any()

        with pd.option_context("use_bottleneck", False):
            result = nanops.nansem(arr, axis=0)
            assert not (result < 0).any()

    @pytest.mark.parametrize(
        "dropna, expected",
        [
            (
                True,
                {
                    "A": [12],
                    "B": [10.0],
                    "C": [1.0],
                    "D": ["a"],
                    "E": Categorical(["a"], categories=["a"]),
                    "F": DatetimeIndex(["2000-01-02"], dtype="M8[ns]"),
                    "G": to_timedelta(["1 days"]),
                },
            ),
            (
                False,
                {
                    "A": [12],
                    "B": [10.0],
                    "C": [np.nan],
                    "D": Series([np.nan], dtype="str"),
                    "E": Categorical([np.nan], categories=["a"]),
                    "F": DatetimeIndex([pd.NaT], dtype="M8[ns]"),
                    "G": to_timedelta([pd.NaT]),
                },
            ),
            (
                True,
                {
                    "H": [8, 9, np.nan, np.nan],
                    "I": [8, 9, np.nan, np.nan],
                    "J": [1, np.nan, np.nan, np.nan],
                    "K": Categorical(["a", np.nan, np.nan, np.nan], categories=["a"]),
                    "L": DatetimeIndex(
                        ["2000-01-02", "NaT", "NaT", "NaT"], dtype="M8[ns]"
                    ),
                    "M": to_timedelta(["1 days", "nan", "nan", "nan"]),
                    "N": [0, 1, 2, 3],
                },
            ),
            (
                False,
                {
                    "H": [8, 9, np.nan, np.nan],
                    "I": [8, 9, np.nan, np.nan],
                    "J": [1, np.nan, np.nan, np.nan],
                    "K": Categorical([np.nan, "a", np.nan, np.nan], categories=["a"]),
                    "L": DatetimeIndex(
                        ["NaT", "2000-01-02", "NaT", "NaT"], dtype="M8[ns]"
                    ),
                    "M": to_timedelta(["nan", "1 days", "nan", "nan"]),
                    "N": [0, 1, 2, 3],
                },
            ),
        ],
    )
    def test_mode_dropna(self, dropna, expected):
        df = DataFrame(
            {
                "A": [12, 12, 19, 11],
                "B": [10, 10, np.nan, 3],
                "C": [1, np.nan, np.nan, np.nan],
                "D": Series([np.nan, np.nan, "a", np.nan], dtype="str"),
                "E": Categorical([np.nan, np.nan, "a", np.nan]),
                "F": DatetimeIndex(["NaT", "2000-01-02", "NaT", "NaT"], dtype="M8[ns]"),
                "G": to_timedelta(["1 days", "nan", "nan", "nan"]),
                "H": [8, 8, 9, 9],
                "I": [9, 9, 8, 8],
                "J": [1, 1, np.nan, np.nan],
                "K": Categorical(["a", np.nan, "a", np.nan]),
                "L": DatetimeIndex(
                    ["2000-01-02", "2000-01-02", "NaT", "NaT"], dtype="M8[ns]"
                ),
                "M": to_timedelta(["1 days", "nan", "1 days", "nan"]),
                "N": np.arange(4, dtype="int64"),
            }
        )

        result = df[sorted(expected.keys())].mode(dropna=dropna)
        expected = DataFrame(expected)
        tm.assert_frame_equal(result, expected)

    def test_mode_sort_with_na(self, using_infer_string):
        df = DataFrame({"A": [np.nan, np.nan, "a", "a"]})
        expected = DataFrame({"A": ["a", np.nan]})
        result = df.mode(dropna=False)
        tm.assert_frame_equal(result, expected)

    def test_mode_empty_df(self):
        df = DataFrame([], columns=["a", "b"])
        result = df.mode()
        expected = DataFrame([], columns=["a", "b"], index=Index([], dtype=np.int64))
        tm.assert_frame_equal(result, expected)

    def test_operators_timedelta64(self):
        df = DataFrame(
            {
                "A": date_range("2012-1-1", periods=3, freq="D"),
                "B": date_range("2012-1-2", periods=3, freq="D"),
                "C": Timestamp("20120101") - timedelta(minutes=5, seconds=5),
            }
        )

        diffs = DataFrame({"A": df["A"] - df["C"], "B": df["A"] - df["B"]})

        # min
        result = diffs.min()
        assert result.iloc[0] == diffs.loc[0, "A"]
        assert result.iloc[1] == diffs.loc[0, "B"]

        result = diffs.min(axis=1)
        assert (result == diffs.loc[0, "B"]).all()

        # max
        result = diffs.max()
        assert result.iloc[0] == diffs.loc[2, "A"]
        assert result.iloc[1] == diffs.loc[2, "B"]

        result = diffs.max(axis=1)
        assert (result == diffs["A"]).all()

        # abs
        result = diffs.abs()
        result2 = abs(diffs)
        expected = DataFrame({"A": df["A"] - df["C"], "B": df["B"] - df["A"]})
        tm.assert_frame_equal(result, expected)
        tm.assert_frame_equal(result2, expected)

        # mixed frame
        mixed = diffs.copy()
        mixed["C"] = "foo"
        mixed["D"] = 1
        mixed["E"] = 1.0
        mixed["F"] = Timestamp("20130101")

        # results in an object array
        result = mixed.min()
        expected = Series(
            [
                pd.Timedelta(timedelta(seconds=5 * 60 + 5)),
                pd.Timedelta(timedelta(days=-1)),
                "foo",
                1,
                1.0,
                Timestamp("20130101"),
            ],
            index=mixed.columns,
        )
        tm.assert_series_equal(result, expected)

        # excludes non-numeric
        result = mixed.min(axis=1, numeric_only=True)
        expected = Series([1, 1, 1.0], index=[0, 1, 2])
        tm.assert_series_equal(result, expected)

        # works when only those columns are selected
        result = mixed[["A", "B"]].min(1)
        expected = Series([timedelta(days=-1)] * 3)
        tm.assert_series_equal(result, expected)

        result = mixed[["A", "B"]].min()
        expected = Series(
            [timedelta(seconds=5 * 60 + 5), timedelta(days=-1)], index=["A", "B"]
        )
        tm.assert_series_equal(result, expected)

        # GH 3106
        df = DataFrame(
            {
                "time": date_range("20130102", periods=5),
                "time2": date_range("20130105", periods=5),
            }
        )
        df["off1"] = df["time2"] - df["time"]
        assert df["off1"].dtype == "timedelta64[ns]"

        df["off2"] = df["time"] - df["time2"]
        df._consolidate_inplace()
        assert df["off1"].dtype == "timedelta64[ns]"
        assert df["off2"].dtype == "timedelta64[ns]"

    def test_std_timedelta64_skipna_false(self):
        # GH#37392
        tdi = pd.timedelta_range("1 Day", periods=10)
        df = DataFrame({"A": tdi, "B": tdi}, copy=True)
        df.iloc[-2, -1] = pd.NaT

        result = df.std(skipna=False)
        expected = Series(
            [df["A"].std(), pd.NaT], index=["A", "B"], dtype="timedelta64[ns]"
        )
        tm.assert_series_equal(result, expected)

        result = df.std(axis=1, skipna=False)
        expected = Series([pd.Timedelta(0)] * 8 + [pd.NaT, pd.Timedelta(0)])
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "values", [["2022-01-01", "2022-01-02", pd.NaT, "2022-01-03"], 4 * [pd.NaT]]
    )
    def test_std_datetime64_with_nat(
        self, values, skipna, using_array_manager, request, unit
    ):
        # GH#51335
        if using_array_manager and (
            not skipna or all(value is pd.NaT for value in values)
        ):
            mark = pytest.mark.xfail(
                reason="GH#51446: Incorrect type inference on NaT in reduction result"
            )
            request.applymarker(mark)
        dti = to_datetime(values).as_unit(unit)
        df = DataFrame({"a": dti})
        result = df.std(skipna=skipna)
        if not skipna or all(value is pd.NaT for value in values):
            expected = Series({"a": pd.NaT}, dtype=f"timedelta64[{unit}]")
        else:
            # 86400000000000ns == 1 day
            expected = Series({"a": 86400000000000}, dtype=f"timedelta64[{unit}]")
        tm.assert_series_equal(result, expected)

    def test_sum_corner(self):
        empty_frame = DataFrame()

        axis0 = empty_frame.sum(0)
        axis1 = empty_frame.sum(1)
        assert isinstance(axis0, Series)
        assert isinstance(axis1, Series)
        assert len(axis0) == 0
        assert len(axis1) == 0

    @pytest.mark.parametrize(
        "index",
        [
            RangeIndex(0),
            DatetimeIndex([]),
            Index([], dtype=np.int64),
            Index([], dtype=np.float64),
            DatetimeIndex([], freq="ME"),
            PeriodIndex([], freq="D"),
        ],
    )
    def test_axis_1_empty(self, all_reductions, index):
        df = DataFrame(columns=["a"], index=index)
        result = getattr(df, all_reductions)(axis=1)
        if all_reductions in ("any", "all"):
            expected_dtype = "bool"
        elif all_reductions == "count":
            expected_dtype = "int64"
        else:
            expected_dtype = "object"
        expected = Series([], index=index, dtype=expected_dtype)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("min_count", [0, 1])
    def test_axis_1_sum_na(self, string_dtype_no_object, skipna, min_count):
        # https://github.com/pandas-dev/pandas/issues/60229
        dtype = string_dtype_no_object
        df = DataFrame({"a": [pd.NA]}, dtype=dtype)
        result = df.sum(axis=1, skipna=skipna, min_count=min_count)
        value = "" if skipna and min_count == 0 else pd.NA
        expected = Series([value], dtype=dtype)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("method, unit", [("sum", 0), ("prod", 1)])
    @pytest.mark.parametrize("numeric_only", [None, True, False])
    def test_sum_prod_nanops(self, method, unit, numeric_only):
        idx = ["a", "b", "c"]
        df = DataFrame({"a": [unit, unit], "b": [unit, np.nan], "c": [np.nan, np.nan]})
        # The default
        result = getattr(df, method)(numeric_only=numeric_only)
        expected = Series([unit, unit, unit], index=idx, dtype="float64")
        tm.assert_series_equal(result, expected)

        # min_count=1
        result = getattr(df, method)(numeric_only=numeric_only, min_count=1)
        expected = Series([unit, unit, np.nan], index=idx)
        tm.assert_series_equal(result, expected)

        # min_count=0
        result = getattr(df, method)(numeric_only=numeric_only, min_count=0)
        expected = Series([unit, unit, unit], index=idx, dtype="float64")
        tm.assert_series_equal(result, expected)

        result = getattr(df.iloc[1:], method)(numeric_only=numeric_only, min_count=1)
        expected = Series([unit, np.nan, np.nan], index=idx)
        tm.assert_series_equal(result, expected)

        # min_count > 1
        df = DataFrame({"A": [unit] * 10, "B": [unit] * 5 + [np.nan] * 5})
        result = getattr(df, method)(numeric_only=numeric_only, min_count=5)
        expected = Series(result, index=["A", "B"])
        tm.assert_series_equal(result, expected)

        result = getattr(df, method)(numeric_only=numeric_only, min_count=6)
        expected = Series(result, index=["A", "B"])
        tm.assert_series_equal(result, expected)

    def test_sum_nanops_timedelta(self):
        # prod isn't defined on timedeltas
        idx = ["a", "b", "c"]
        df = DataFrame({"a": [0, 0], "b": [0, np.nan], "c": [np.nan, np.nan]})

        df2 = df.apply(to_timedelta)

        # 0 by default
        result = df2.sum()
        expected = Series([0, 0, 0], dtype="m8[ns]", index=idx)
        tm.assert_series_equal(result, expected)

        # min_count=0
        result = df2.sum(min_count=0)
        tm.assert_series_equal(result, expected)

        # min_count=1
        result = df2.sum(min_count=1)
        expected = Series([0, 0, np.nan], dtype="m8[ns]", index=idx)
        tm.assert_series_equal(result, expected)

    def test_sum_nanops_min_count(self):
        # https://github.com/pandas-dev/pandas/issues/39738
        df = DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
        result = df.sum(min_count=10)
        expected = Series([np.nan, np.nan], index=["x", "y"])
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("float_type", ["float16", "float32", "float64"])
    @pytest.mark.parametrize(
        "kwargs, expected_result",
        [
            ({"axis": 1, "min_count": 2}, [3.2, 5.3, np.nan]),
            ({"axis": 1, "min_count": 3}, [np.nan, np.nan, np.nan]),
            ({"axis": 1, "skipna": False}, [3.2, 5.3, np.nan]),
        ],
    )
    def test_sum_nanops_dtype_min_count(self, float_type, kwargs, expected_result):
        # GH#46947
        df = DataFrame({"a": [1.0, 2.3, 4.4], "b": [2.2, 3, np.nan]}, dtype=float_type)
        result = df.sum(**kwargs)
        expected = Series(expected_result).astype(float_type)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("float_type", ["float16", "float32", "float64"])
    @pytest.mark.parametrize(
        "kwargs, expected_result",
        [
            ({"axis": 1, "min_count": 2}, [2.0, 4.0, np.nan]),
            ({"axis": 1, "min_count": 3}, [np.nan, np.nan, np.nan]),
            ({"axis": 1, "skipna": False}, [2.0, 4.0, np.nan]),
        ],
    )
    def test_prod_nanops_dtype_min_count(self, float_type, kwargs, expected_result):
        # GH#46947
        df = DataFrame(
            {"a": [1.0, 2.0, 4.4], "b": [2.0, 2.0, np.nan]}, dtype=float_type
        )
        result = df.prod(**kwargs)
        expected = Series(expected_result).astype(float_type)
        tm.assert_series_equal(result, expected)

    def test_sum_object(self, float_frame):
        values = float_frame.values.astype(int)
        frame = DataFrame(values, index=float_frame.index, columns=float_frame.columns)
        deltas = frame * timedelta(1)
        deltas.sum()

    def test_sum_bool(self, float_frame):
        # ensure this works, bug report
        bools = np.isnan(float_frame)
        bools.sum(1)
        bools.sum(0)

    def test_sum_mixed_datetime(self):
        # GH#30886
        df = DataFrame({"A": date_range("2000", periods=4), "B": [1, 2, 3, 4]}).reindex(
            [2, 3, 4]
        )
        with pytest.raises(TypeError, match="does not support reduction 'sum'"):
            df.sum()

    def test_mean_corner(self, float_frame, float_string_frame):
        # unit test when have object data
        msg = "Could not convert|does not support|Cannot perform"
        with pytest.raises(TypeError, match=msg):
            float_string_frame.mean(axis=0)

        # xs sum mixed type, just want to know it works...
        with pytest.raises(TypeError, match="unsupported operand type"):
            float_string_frame.mean(axis=1)

        # take mean of boolean column
        float_frame["bool"] = float_frame["A"] > 0
        means = float_frame.mean(0)
        assert means["bool"] == float_frame["bool"].values.mean()

    def test_mean_datetimelike(self):
        # GH#24757 check that datetimelike are excluded by default, handled
        #  correctly with numeric_only=True
        #  As of 2.0, datetimelike are *not* excluded with numeric_only=None

        df = DataFrame(
            {
                "A": np.arange(3),
                "B": date_range("2016-01-01", periods=3),
                "C": pd.timedelta_range("1D", periods=3),
                "D": pd.period_range("2016", periods=3, freq="Y"),
            }
        )
        result = df.mean(numeric_only=True)
        expected = Series({"A": 1.0})
        tm.assert_series_equal(result, expected)

        with pytest.raises(TypeError, match="mean is not implemented for PeriodArray"):
            df.mean()

    def test_mean_datetimelike_numeric_only_false(self):
        df = DataFrame(
            {
                "A": np.arange(3),
                "B": date_range("2016-01-01", periods=3),
                "C": pd.timedelta_range("1D", periods=3),
            }
        )

        # datetime(tz) and timedelta work
        result = df.mean(numeric_only=False)
        expected = Series({"A": 1, "B": df.loc[1, "B"], "C": df.loc[1, "C"]})
        tm.assert_series_equal(result, expected)

        # mean of period is not allowed
        df["D"] = pd.period_range("2016", periods=3, freq="Y")

        with pytest.raises(TypeError, match="mean is not implemented for Period"):
            df.mean(numeric_only=False)

    def test_mean_extensionarray_numeric_only_true(self):
        # https://github.com/pandas-dev/pandas/issues/33256
        arr = np.random.default_rng(2).integers(1000, size=(10, 5))
        df = DataFrame(arr, dtype="Int64")
        result = df.mean(numeric_only=True)
        expected = DataFrame(arr).mean().astype("Float64")
        tm.assert_series_equal(result, expected)

    def test_stats_mixed_type(self, float_string_frame):
        with pytest.raises(TypeError, match="could not convert"):
            float_string_frame.std(1)
        with pytest.raises(TypeError, match="could not convert"):
            float_string_frame.var(1)
        with pytest.raises(TypeError, match="unsupported operand type"):
            float_string_frame.mean(1)
        with pytest.raises(TypeError, match="could not convert"):
            float_string_frame.skew(1)

    def test_sum_bools(self):
        df = DataFrame(index=range(1), columns=range(10))
        bools = isna(df)
        assert bools.sum(axis=1)[0] == 10

    # ----------------------------------------------------------------------
    # Index of max / min

    @pytest.mark.parametrize("skipna", [True, False])
    @pytest.mark.parametrize("axis", [0, 1])
    def test_idxmin(self, float_frame, int_frame, skipna, axis):
        frame = float_frame
        frame.iloc[5:10] = np.nan
        frame.iloc[15:20, -2:] = np.nan
        for df in [frame, int_frame]:
            warn = None
            if skipna is False or axis == 1:
                warn = None if df is int_frame else FutureWarning
            msg = "The behavior of DataFrame.idxmin with all-NA values"
            with tm.assert_produces_warning(warn, match=msg):
                result = df.idxmin(axis=axis, skipna=skipna)

            msg2 = "The behavior of Series.idxmin"
            with tm.assert_produces_warning(warn, match=msg2):
                expected = df.apply(Series.idxmin, axis=axis, skipna=skipna)
            expected = expected.astype(df.index.dtype)
            tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("axis", [0, 1])
    @pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
    def test_idxmin_empty(self, index, skipna, axis):
        # GH53265
        if axis == 0:
            frame = DataFrame(index=index)
        else:
            frame = DataFrame(columns=index)

        result = frame.idxmin(axis=axis, skipna=skipna)
        expected = Series(dtype=index.dtype)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("numeric_only", [True, False])
    def test_idxmin_numeric_only(self, numeric_only):
        df = DataFrame({"a": [2, 3, 1], "b": [2, 1, 1], "c": list("xyx")})
        result = df.idxmin(numeric_only=numeric_only)
        if numeric_only:
            expected = Series([2, 1], index=["a", "b"])
        else:
            expected = Series([2, 1, 0], index=["a", "b", "c"])
        tm.assert_series_equal(result, expected)

    def test_idxmin_axis_2(self, float_frame):
        frame = float_frame
        msg = "No axis named 2 for object type DataFrame"
        with pytest.raises(ValueError, match=msg):
            frame.idxmin(axis=2)

    @pytest.mark.parametrize("axis", [0, 1])
    def test_idxmax(self, float_frame, int_frame, skipna, axis):
        frame = float_frame
        frame.iloc[5:10] = np.nan
        frame.iloc[15:20, -2:] = np.nan
        for df in [frame, int_frame]:
            warn = None
            if skipna is False or axis == 1:
                warn = None if df is int_frame else FutureWarning
            msg = "The behavior of DataFrame.idxmax with all-NA values"
            with tm.assert_produces_warning(warn, match=msg):
                result = df.idxmax(axis=axis, skipna=skipna)

            msg2 = "The behavior of Series.idxmax"
            with tm.assert_produces_warning(warn, match=msg2):
                expected = df.apply(Series.idxmax, axis=axis, skipna=skipna)
            expected = expected.astype(df.index.dtype)
            tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("axis", [0, 1])
    @pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
    def test_idxmax_empty(self, index, skipna, axis):
        # GH53265
        if axis == 0:
            frame = DataFrame(index=index)
        else:
            frame = DataFrame(columns=index)

        result = frame.idxmax(axis=axis, skipna=skipna)
        expected = Series(dtype=index.dtype)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("numeric_only", [True, False])
    def test_idxmax_numeric_only(self, numeric_only):
        df = DataFrame({"a": [2, 3, 1], "b": [2, 1, 1], "c": list("xyx")})
        result = df.idxmax(numeric_only=numeric_only)
        if numeric_only:
            expected = Series([1, 0], index=["a", "b"])
        else:
            expected = Series([1, 0, 1], index=["a", "b", "c"])
        tm.assert_series_equal(result, expected)

    def test_idxmax_arrow_types(self):
        # GH#55368
        pytest.importorskip("pyarrow")

        df = DataFrame({"a": [2, 3, 1], "b": [2, 1, 1]}, dtype="int64[pyarrow]")
        result = df.idxmax()
        expected = Series([1, 0], index=["a", "b"])
        tm.assert_series_equal(result, expected)

        result = df.idxmin()
        expected = Series([2, 1], index=["a", "b"])
        tm.assert_series_equal(result, expected)

        df = DataFrame({"a": ["b", "c", "a"]}, dtype="string[pyarrow]")
        result = df.idxmax(numeric_only=False)
        expected = Series([1], index=["a"])
        tm.assert_series_equal(result, expected)

        result = df.idxmin(numeric_only=False)
        expected = Series([2], index=["a"])
        tm.assert_series_equal(result, expected)

    def test_idxmax_axis_2(self, float_frame):
        frame = float_frame
        msg = "No axis named 2 for object type DataFrame"
        with pytest.raises(ValueError, match=msg):
            frame.idxmax(axis=2)

    def test_idxmax_mixed_dtype(self):
        # don't cast to object, which would raise in nanops
        dti = date_range("2016-01-01", periods=3)

        # Copying dti is needed for ArrayManager otherwise when we set
        #  df.loc[0, 3] = pd.NaT below it edits dti
        df = DataFrame({1: [0, 2, 1], 2: range(3)[::-1], 3: dti.copy(deep=True)})

        result = df.idxmax()
        expected = Series([1, 0, 2], index=[1, 2, 3])
        tm.assert_series_equal(result, expected)

        result = df.idxmin()
        expected = Series([0, 2, 0], index=[1, 2, 3])
        tm.assert_series_equal(result, expected)

        # with NaTs
        df.loc[0, 3] = pd.NaT
        result = df.idxmax()
        expected = Series([1, 0, 2], index=[1, 2, 3])
        tm.assert_series_equal(result, expected)

        result = df.idxmin()
        expected = Series([0, 2, 1], index=[1, 2, 3])
        tm.assert_series_equal(result, expected)

        # with multi-column dt64 block
        df[4] = dti[::-1]
        df._consolidate_inplace()

        result = df.idxmax()
        expected = Series([1, 0, 2, 0], index=[1, 2, 3, 4])
        tm.assert_series_equal(result, expected)

        result = df.idxmin()
        expected = Series([0, 2, 1, 2], index=[1, 2, 3, 4])
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "op, expected_value",
        [("idxmax", [0, 4]), ("idxmin", [0, 5])],
    )
    def test_idxmax_idxmin_convert_dtypes(self, op, expected_value):
        # GH 40346
        df = DataFrame(
            {
                "ID": [100, 100, 100, 200, 200, 200],
                "value": [0, 0, 0, 1, 2, 0],
            },
            dtype="Int64",
        )
        df = df.groupby("ID")

        result = getattr(df, op)()
        expected = DataFrame(
            {"value": expected_value},
            index=Index([100, 200], name="ID", dtype="Int64"),
        )
        tm.assert_frame_equal(result, expected)

    def test_idxmax_dt64_multicolumn_axis1(self):
        dti = date_range("2016-01-01", periods=3)
        df = DataFrame({3: dti, 4: dti[::-1]}, copy=True)
        df.iloc[0, 0] = pd.NaT

        df._consolidate_inplace()

        result = df.idxmax(axis=1)
        expected = Series([4, 3, 3])
        tm.assert_series_equal(result, expected)

        result = df.idxmin(axis=1)
        expected = Series([4, 3, 4])
        tm.assert_series_equal(result, expected)

    # ----------------------------------------------------------------------
    # Logical reductions

    @pytest.mark.parametrize("opname", ["any", "all"])
    @pytest.mark.parametrize("axis", [0, 1])
    @pytest.mark.parametrize("bool_only", [False, True])
    def test_any_all_mixed_float(self, opname, axis, bool_only, float_string_frame):
        # make sure op works on mixed-type frame
        mixed = float_string_frame
        mixed["_bool_"] = np.random.default_rng(2).standard_normal(len(mixed)) > 0.5

        getattr(mixed, opname)(axis=axis, bool_only=bool_only)

    @pytest.mark.parametrize("opname", ["any", "all"])
    @pytest.mark.parametrize("axis", [0, 1])
    def test_any_all_bool_with_na(self, opname, axis, bool_frame_with_na):
        getattr(bool_frame_with_na, opname)(axis=axis, bool_only=False)

    @pytest.mark.filterwarnings("ignore:Downcasting object dtype arrays:FutureWarning")
    @pytest.mark.parametrize("opname", ["any", "all"])
    def test_any_all_bool_frame(self, opname, bool_frame_with_na):
        # GH#12863: numpy gives back non-boolean data for object type
        # so fill NaNs to compare with pandas behavior
        frame = bool_frame_with_na.fillna(True)
        alternative = getattr(np, opname)
        f = getattr(frame, opname)

        def skipna_wrapper(x):
            nona = x.dropna().values
            return alternative(nona)

        def wrapper(x):
            return alternative(x.values)

        result0 = f(axis=0, skipna=False)
        result1 = f(axis=1, skipna=False)

        tm.assert_series_equal(result0, frame.apply(wrapper))
        tm.assert_series_equal(result1, frame.apply(wrapper, axis=1))

        result0 = f(axis=0)
        result1 = f(axis=1)

        tm.assert_series_equal(result0, frame.apply(skipna_wrapper))
        tm.assert_series_equal(
            result1, frame.apply(skipna_wrapper, axis=1), check_dtype=False
        )

        # bad axis
        with pytest.raises(ValueError, match="No axis named 2"):
            f(axis=2)

        # all NA case
        all_na = frame * np.nan
        r0 = getattr(all_na, opname)(axis=0)
        r1 = getattr(all_na, opname)(axis=1)
        if opname == "any":
            assert not r0.any()
            assert not r1.any()
        else:
            assert r0.all()
            assert r1.all()

    def test_any_all_extra(self):
        df = DataFrame(
            {
                "A": [True, False, False],
                "B": [True, True, False],
                "C": [True, True, True],
            },
            index=["a", "b", "c"],
        )
        result = df[["A", "B"]].any(axis=1)
        expected = Series([True, True, False], index=["a", "b", "c"])
        tm.assert_series_equal(result, expected)

        result = df[["A", "B"]].any(axis=1, bool_only=True)
        tm.assert_series_equal(result, expected)

        result = df.all(1)
        expected = Series([True, False, False], index=["a", "b", "c"])
        tm.assert_series_equal(result, expected)

        result = df.all(1, bool_only=True)
        tm.assert_series_equal(result, expected)

        # Axis is None
        result = df.all(axis=None).item()
        assert result is False

        result = df.any(axis=None).item()
        assert result is True

        result = df[["C"]].all(axis=None).item()
        assert result is True

    @pytest.mark.parametrize("axis", [0, 1])
    @pytest.mark.parametrize("bool_agg_func", ["any", "all"])
    @pytest.mark.parametrize("skipna", [True, False])
    def test_any_all_object_dtype(self, axis, bool_agg_func, skipna):
        # GH#35450
        df = DataFrame(
            data=[
                [1, np.nan, np.nan, True],
                [np.nan, 2, np.nan, True],
                [np.nan, np.nan, np.nan, True],
                [np.nan, np.nan, "5", np.nan],
            ]
        )
        result = getattr(df, bool_agg_func)(axis=axis, skipna=skipna)
        expected = Series([True, True, True, True])
        tm.assert_series_equal(result, expected)

    # GH#50947 deprecates this but it is not emitting a warning in some builds.
    @pytest.mark.filterwarnings(
        "ignore:'any' with datetime64 dtypes is deprecated.*:FutureWarning"
    )
    def test_any_datetime(self):
        # GH 23070
        float_data = [1, np.nan, 3, np.nan]
        datetime_data = [
            Timestamp("1960-02-15"),
            Timestamp("1960-02-16"),
            pd.NaT,
            pd.NaT,
        ]
        df = DataFrame({"A": float_data, "B": datetime_data})

        result = df.any(axis=1)

        expected = Series([True, True, True, False])
        tm.assert_series_equal(result, expected)

    def test_any_all_bool_only(self):
        # GH 25101
        df = DataFrame(
            {"col1": [1, 2, 3], "col2": [4, 5, 6], "col3": [None, None, None]},
            columns=Index(["col1", "col2", "col3"], dtype=object),
        )

        result = df.all(bool_only=True)
        expected = Series(dtype=np.bool_, index=[])
        tm.assert_series_equal(result, expected)

        df = DataFrame(
            {
                "col1": [1, 2, 3],
                "col2": [4, 5, 6],
                "col3": [None, None, None],
                "col4": [False, False, True],
            }
        )

        result = df.all(bool_only=True)
        expected = Series({"col4": False})
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "func, data, expected",
        [
            (np.any, {}, False),
            (np.all, {}, True),
            (np.any, {"A": []}, False),
            (np.all, {"A": []}, True),
            (np.any, {"A": [False, False]}, False),
            (np.all, {"A": [False, False]}, False),
            (np.any, {"A": [True, False]}, True),
            (np.all, {"A": [True, False]}, False),
            (np.any, {"A": [True, True]}, True),
            (np.all, {"A": [True, True]}, True),
            (np.any, {"A": [False], "B": [False]}, False),
            (np.all, {"A": [False], "B": [False]}, False),
            (np.any, {"A": [False, False], "B": [False, True]}, True),
            (np.all, {"A": [False, False], "B": [False, True]}, False),
            # other types
            (np.all, {"A": Series([0.0, 1.0], dtype="float")}, False),
            (np.any, {"A": Series([0.0, 1.0], dtype="float")}, True),
            (np.all, {"A": Series([0, 1], dtype=int)}, False),
            (np.any, {"A": Series([0, 1], dtype=int)}, True),
            pytest.param(np.all, {"A": Series([0, 1], dtype="M8[ns]")}, False),
            pytest.param(np.all, {"A": Series([0, 1], dtype="M8[ns, UTC]")}, False),
            pytest.param(np.any, {"A": Series([0, 1], dtype="M8[ns]")}, True),
            pytest.param(np.any, {"A": Series([0, 1], dtype="M8[ns, UTC]")}, True),
            pytest.param(np.all, {"A": Series([1, 2], dtype="M8[ns]")}, True),
            pytest.param(np.all, {"A": Series([1, 2], dtype="M8[ns, UTC]")}, True),
            pytest.param(np.any, {"A": Series([1, 2], dtype="M8[ns]")}, True),
            pytest.param(np.any, {"A": Series([1, 2], dtype="M8[ns, UTC]")}, True),
            pytest.param(np.all, {"A": Series([0, 1], dtype="m8[ns]")}, False),
            pytest.param(np.any, {"A": Series([0, 1], dtype="m8[ns]")}, True),
            pytest.param(np.all, {"A": Series([1, 2], dtype="m8[ns]")}, True),
            pytest.param(np.any, {"A": Series([1, 2], dtype="m8[ns]")}, True),
            # np.all on Categorical raises, so the reduction drops the
            #  column, so all is being done on an empty Series, so is True
            (np.all, {"A": Series([0, 1], dtype="category")}, True),
            (np.any, {"A": Series([0, 1], dtype="category")}, False),
            (np.all, {"A": Series([1, 2], dtype="category")}, True),
            (np.any, {"A": Series([1, 2], dtype="category")}, False),
            # Mix GH#21484
            pytest.param(
                np.all,
                {
                    "A": Series([10, 20], dtype="M8[ns]"),
                    "B": Series([10, 20], dtype="m8[ns]"),
                },
                True,
            ),
        ],
    )
    def test_any_all_np_func(self, func, data, expected):
        # GH 19976
        data = DataFrame(data)

        if any(isinstance(x, CategoricalDtype) for x in data.dtypes):
            with pytest.raises(
                TypeError, match="dtype category does not support reduction"
            ):
                func(data)

            # method version
            with pytest.raises(
                TypeError, match="dtype category does not support reduction"
            ):
                getattr(DataFrame(data), func.__name__)(axis=None)
        else:
            msg = "'(any|all)' with datetime64 dtypes is deprecated"
            if data.dtypes.apply(lambda x: x.kind == "M").any():
                warn = FutureWarning
            else:
                warn = None

            with tm.assert_produces_warning(warn, match=msg, check_stacklevel=False):
                # GH#34479
                result = func(data)
            assert isinstance(result, np.bool_)
            assert result.item() is expected

            # method version
            with tm.assert_produces_warning(warn, match=msg):
                # GH#34479
                result = getattr(DataFrame(data), func.__name__)(axis=None)
            assert isinstance(result, np.bool_)
            assert result.item() is expected

    def test_any_all_object(self):
        # GH 19976
        result = np.all(DataFrame(columns=["a", "b"])).item()
        assert result is True

        result = np.any(DataFrame(columns=["a", "b"])).item()
        assert result is False

    def test_any_all_object_bool_only(self):
        df = DataFrame({"A": ["foo", 2], "B": [True, False]}).astype(object)
        df._consolidate_inplace()
        df["C"] = Series([True, True])

        # Categorical of bools is _not_ considered booly
        df["D"] = df["C"].astype("category")

        # The underlying bug is in DataFrame._get_bool_data, so we check
        #  that while we're here
        res = df._get_bool_data()
        expected = df[["C"]]
        tm.assert_frame_equal(res, expected)

        res = df.all(bool_only=True, axis=0)
        expected = Series([True], index=["C"])
        tm.assert_series_equal(res, expected)

        # operating on a subset of columns should not produce a _larger_ Series
        res = df[["B", "C"]].all(bool_only=True, axis=0)
        tm.assert_series_equal(res, expected)

        assert df.all(bool_only=True, axis=None)

        res = df.any(bool_only=True, axis=0)
        expected = Series([True], index=["C"])
        tm.assert_series_equal(res, expected)

        # operating on a subset of columns should not produce a _larger_ Series
        res = df[["C"]].any(bool_only=True, axis=0)
        tm.assert_series_equal(res, expected)

        assert df.any(bool_only=True, axis=None)

    # ---------------------------------------------------------------------
    # Unsorted

    def test_series_broadcasting(self):
        # smoke test for numpy warnings
        # GH 16378, GH 16306
        df = DataFrame([1.0, 1.0, 1.0])
        df_nan = DataFrame({"A": [np.nan, 2.0, np.nan]})
        s = Series([1, 1, 1])
        s_nan = Series([np.nan, np.nan, 1])

        with tm.assert_produces_warning(None):
            df_nan.clip(lower=s, axis=0)
            for op in ["lt", "le", "gt", "ge", "eq", "ne"]:
                getattr(df, op)(s_nan, axis=0)


class TestDataFrameReductions:
    def test_min_max_dt64_with_NaT(self):
        # Both NaT and Timestamp are in DataFrame.
        df = DataFrame({"foo": [pd.NaT, pd.NaT, Timestamp("2012-05-01")]})

        res = df.min()
        exp = Series([Timestamp("2012-05-01")], index=["foo"])
        tm.assert_series_equal(res, exp)

        res = df.max()
        exp = Series([Timestamp("2012-05-01")], index=["foo"])
        tm.assert_series_equal(res, exp)

        # GH12941, only NaTs are in DataFrame.
        df = DataFrame({"foo": [pd.NaT, pd.NaT]})

        res = df.min()
        exp = Series([pd.NaT], index=["foo"])
        tm.assert_series_equal(res, exp)

        res = df.max()
        exp = Series([pd.NaT], index=["foo"])
        tm.assert_series_equal(res, exp)

    def test_min_max_dt64_with_NaT_skipna_false(self, request, tz_naive_fixture):
        # GH#36907
        tz = tz_naive_fixture
        if isinstance(tz, tzlocal) and is_platform_windows():
            pytest.skip(
                "GH#37659 OSError raised within tzlocal bc Windows "
                "chokes in times before 1970-01-01"
            )

        df = DataFrame(
            {
                "a": [
                    Timestamp("2020-01-01 08:00:00", tz=tz),
                    Timestamp("1920-02-01 09:00:00", tz=tz),
                ],
                "b": [Timestamp("2020-02-01 08:00:00", tz=tz), pd.NaT],
            }
        )
        res = df.min(axis=1, skipna=False)
        expected = Series([df.loc[0, "a"], pd.NaT])
        assert expected.dtype == df["a"].dtype

        tm.assert_series_equal(res, expected)

        res = df.max(axis=1, skipna=False)
        expected = Series([df.loc[0, "b"], pd.NaT])
        assert expected.dtype == df["a"].dtype

        tm.assert_series_equal(res, expected)

    def test_min_max_dt64_api_consistency_with_NaT(self):
        # Calling the following sum functions returned an error for dataframes but
        # returned NaT for series. These tests check that the API is consistent in
        # min/max calls on empty Series/DataFrames. See GH:33704 for more
        # information
        df = DataFrame({"x": to_datetime([])})
        expected_dt_series = Series(to_datetime([]))
        # check axis 0
        assert (df.min(axis=0).x is pd.NaT) == (expected_dt_series.min() is pd.NaT)
        assert (df.max(axis=0).x is pd.NaT) == (expected_dt_series.max() is pd.NaT)

        # check axis 1
        tm.assert_series_equal(df.min(axis=1), expected_dt_series)
        tm.assert_series_equal(df.max(axis=1), expected_dt_series)

    def test_min_max_dt64_api_consistency_empty_df(self):
        # check DataFrame/Series api consistency when calling min/max on an empty
        # DataFrame/Series.
        df = DataFrame({"x": []})
        expected_float_series = Series([], dtype=float)
        # check axis 0
        assert np.isnan(df.min(axis=0).x) == np.isnan(expected_float_series.min())
        assert np.isnan(df.max(axis=0).x) == np.isnan(expected_float_series.max())
        # check axis 1
        tm.assert_series_equal(df.min(axis=1), expected_float_series)
        tm.assert_series_equal(df.min(axis=1), expected_float_series)

    @pytest.mark.parametrize(
        "initial",
        ["2018-10-08 13:36:45+00:00", "2018-10-08 13:36:45+03:00"],  # Non-UTC timezone
    )
    @pytest.mark.parametrize("method", ["min", "max"])
    def test_preserve_timezone(self, initial: str, method):
        # GH 28552
        initial_dt = to_datetime(initial)
        expected = Series([initial_dt])
        df = DataFrame([expected])
        result = getattr(df, method)(axis=1)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("method", ["min", "max"])
    def test_minmax_tzaware_skipna_axis_1(self, method, skipna):
        # GH#51242
        val = to_datetime("1900-01-01", utc=True)
        df = DataFrame(
            {"a": Series([pd.NaT, pd.NaT, val]), "b": Series([pd.NaT, val, val])}
        )
        op = getattr(df, method)
        result = op(axis=1, skipna=skipna)
        if skipna:
            expected = Series([pd.NaT, val, val])
        else:
            expected = Series([pd.NaT, pd.NaT, val])
        tm.assert_series_equal(result, expected)

    def test_frame_any_with_timedelta(self):
        # GH#17667
        df = DataFrame(
            {
                "a": Series([0, 0]),
                "t": Series([to_timedelta(0, "s"), to_timedelta(1, "ms")]),
            }
        )

        result = df.any(axis=0)
        expected = Series(data=[False, True], index=["a", "t"])
        tm.assert_series_equal(result, expected)

        result = df.any(axis=1)
        expected = Series(data=[False, True])
        tm.assert_series_equal(result, expected)

    def test_reductions_skipna_none_raises(
        self, request, frame_or_series, all_reductions
    ):
        if all_reductions == "count":
            request.applymarker(
                pytest.mark.xfail(reason="Count does not accept skipna")
            )
        obj = frame_or_series([1, 2, 3])
        msg = 'For argument "skipna" expected type bool, received type NoneType.'
        with pytest.raises(ValueError, match=msg):
            getattr(obj, all_reductions)(skipna=None)

    @td.skip_array_manager_invalid_test
    def test_reduction_timestamp_smallest_unit(self):
        # GH#52524
        df = DataFrame(
            {
                "a": Series([Timestamp("2019-12-31")], dtype="datetime64[s]"),
                "b": Series(
                    [Timestamp("2019-12-31 00:00:00.123")], dtype="datetime64[ms]"
                ),
            }
        )
        result = df.max()
        expected = Series(
            [Timestamp("2019-12-31"), Timestamp("2019-12-31 00:00:00.123")],
            dtype="datetime64[ms]",
            index=["a", "b"],
        )
        tm.assert_series_equal(result, expected)

    @td.skip_array_manager_not_yet_implemented
    def test_reduction_timedelta_smallest_unit(self):
        # GH#52524
        df = DataFrame(
            {
                "a": Series([pd.Timedelta("1 days")], dtype="timedelta64[s]"),
                "b": Series([pd.Timedelta("1 days")], dtype="timedelta64[ms]"),
            }
        )
        result = df.max()
        expected = Series(
            [pd.Timedelta("1 days"), pd.Timedelta("1 days")],
            dtype="timedelta64[ms]",
            index=["a", "b"],
        )
        tm.assert_series_equal(result, expected)


class TestNuisanceColumns:
    @pytest.mark.parametrize("method", ["any", "all"])
    def test_any_all_categorical_dtype_nuisance_column(self, method):
        # GH#36076 DataFrame should match Series behavior
        ser = Series([0, 1], dtype="category", name="A")
        df = ser.to_frame()

        # Double-check the Series behavior is to raise
        with pytest.raises(TypeError, match="does not support reduction"):
            getattr(ser, method)()

        with pytest.raises(TypeError, match="does not support reduction"):
            getattr(np, method)(ser)

        with pytest.raises(TypeError, match="does not support reduction"):
            getattr(df, method)(bool_only=False)

        with pytest.raises(TypeError, match="does not support reduction"):
            getattr(df, method)(bool_only=None)

        with pytest.raises(TypeError, match="does not support reduction"):
            getattr(np, method)(df, axis=0)

    def test_median_categorical_dtype_nuisance_column(self):
        # GH#21020 DataFrame.median should match Series.median
        df = DataFrame({"A": Categorical([1, 2, 2, 2, 3])})
        ser = df["A"]

        # Double-check the Series behavior is to raise
        with pytest.raises(TypeError, match="does not support reduction"):
            ser.median()

        with pytest.raises(TypeError, match="does not support reduction"):
            df.median(numeric_only=False)

        with pytest.raises(TypeError, match="does not support reduction"):
            df.median()

        # same thing, but with an additional non-categorical column
        df["B"] = df["A"].astype(int)

        with pytest.raises(TypeError, match="does not support reduction"):
            df.median(numeric_only=False)

        with pytest.raises(TypeError, match="does not support reduction"):
            df.median()

        # TODO: np.median(df, axis=0) gives np.array([2.0, 2.0]) instead
        #  of expected.values

    @pytest.mark.parametrize("method", ["min", "max"])
    def test_min_max_categorical_dtype_non_ordered_nuisance_column(self, method):
        # GH#28949 DataFrame.min should behave like Series.min
        cat = Categorical(["a", "b", "c", "b"], ordered=False)
        ser = Series(cat)
        df = ser.to_frame("A")

        # Double-check the Series behavior
        with pytest.raises(TypeError, match="is not ordered for operation"):
            getattr(ser, method)()

        with pytest.raises(TypeError, match="is not ordered for operation"):
            getattr(np, method)(ser)

        with pytest.raises(TypeError, match="is not ordered for operation"):
            getattr(df, method)(numeric_only=False)

        with pytest.raises(TypeError, match="is not ordered for operation"):
            getattr(df, method)()

        with pytest.raises(TypeError, match="is not ordered for operation"):
            getattr(np, method)(df, axis=0)

        # same thing, but with an additional non-categorical column
        df["B"] = df["A"].astype(object)
        with pytest.raises(TypeError, match="is not ordered for operation"):
            getattr(df, method)()

        with pytest.raises(TypeError, match="is not ordered for operation"):
            getattr(np, method)(df, axis=0)


class TestEmptyDataFrameReductions:
    @pytest.mark.parametrize(
        "opname, dtype, exp_value, exp_dtype",
        [
            ("sum", np.int8, 0, np.int64),
            ("prod", np.int8, 1, np.int_),
            ("sum", np.int64, 0, np.int64),
            ("prod", np.int64, 1, np.int64),
            ("sum", np.uint8, 0, np.uint64),
            ("prod", np.uint8, 1, np.uint),
            ("sum", np.uint64, 0, np.uint64),
            ("prod", np.uint64, 1, np.uint64),
            ("sum", np.float32, 0, np.float32),
            ("prod", np.float32, 1, np.float32),
            ("sum", np.float64, 0, np.float64),
        ],
    )
    def test_df_empty_min_count_0(self, opname, dtype, exp_value, exp_dtype):
        df = DataFrame({0: [], 1: []}, dtype=dtype)
        result = getattr(df, opname)(min_count=0)

        expected = Series([exp_value, exp_value], dtype=exp_dtype)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "opname, dtype, exp_dtype",
        [
            ("sum", np.int8, np.float64),
            ("prod", np.int8, np.float64),
            ("sum", np.int64, np.float64),
            ("prod", np.int64, np.float64),
            ("sum", np.uint8, np.float64),
            ("prod", np.uint8, np.float64),
            ("sum", np.uint64, np.float64),
            ("prod", np.uint64, np.float64),
            ("sum", np.float32, np.float32),
            ("prod", np.float32, np.float32),
            ("sum", np.float64, np.float64),
        ],
    )
    def test_df_empty_min_count_1(self, opname, dtype, exp_dtype):
        df = DataFrame({0: [], 1: []}, dtype=dtype)
        result = getattr(df, opname)(min_count=1)

        expected = Series([np.nan, np.nan], dtype=exp_dtype)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "opname, dtype, exp_value, exp_dtype",
        [
            ("sum", "Int8", 0, ("Int32" if is_windows_np2_or_is32 else "Int64")),
            ("prod", "Int8", 1, ("Int32" if is_windows_np2_or_is32 else "Int64")),
            ("prod", "Int8", 1, ("Int32" if is_windows_np2_or_is32 else "Int64")),
            ("sum", "Int64", 0, "Int64"),
            ("prod", "Int64", 1, "Int64"),
            ("sum", "UInt8", 0, ("UInt32" if is_windows_np2_or_is32 else "UInt64")),
            ("prod", "UInt8", 1, ("UInt32" if is_windows_np2_or_is32 else "UInt64")),
            ("sum", "UInt64", 0, "UInt64"),
            ("prod", "UInt64", 1, "UInt64"),
            ("sum", "Float32", 0, "Float32"),
            ("prod", "Float32", 1, "Float32"),
            ("sum", "Float64", 0, "Float64"),
        ],
    )
    def test_df_empty_nullable_min_count_0(self, opname, dtype, exp_value, exp_dtype):
        df = DataFrame({0: [], 1: []}, dtype=dtype)
        result = getattr(df, opname)(min_count=0)

        expected = Series([exp_value, exp_value], dtype=exp_dtype)
        tm.assert_series_equal(result, expected)

    # TODO: why does min_count=1 impact the resulting Windows dtype
    # differently than min_count=0?
    @pytest.mark.parametrize(
        "opname, dtype, exp_dtype",
        [
            ("sum", "Int8", ("Int32" if is_windows_or_is32 else "Int64")),
            ("prod", "Int8", ("Int32" if is_windows_or_is32 else "Int64")),
            ("sum", "Int64", "Int64"),
            ("prod", "Int64", "Int64"),
            ("sum", "UInt8", ("UInt32" if is_windows_or_is32 else "UInt64")),
            ("prod", "UInt8", ("UInt32" if is_windows_or_is32 else "UInt64")),
            ("sum", "UInt64", "UInt64"),
            ("prod", "UInt64", "UInt64"),
            ("sum", "Float32", "Float32"),
            ("prod", "Float32", "Float32"),
            ("sum", "Float64", "Float64"),
        ],
    )
    def test_df_empty_nullable_min_count_1(self, opname, dtype, exp_dtype):
        df = DataFrame({0: [], 1: []}, dtype=dtype)
        result = getattr(df, opname)(min_count=1)

        expected = Series([pd.NA, pd.NA], dtype=exp_dtype)
        tm.assert_series_equal(result, expected)


def test_sum_timedelta64_skipna_false(using_array_manager, request):
    # GH#17235
    if using_array_manager:
        mark = pytest.mark.xfail(
            reason="Incorrect type inference on NaT in reduction result"
        )
        request.applymarker(mark)

    arr = np.arange(8).astype(np.int64).view("m8[s]").reshape(4, 2)
    arr[-1, -1] = "Nat"

    df = DataFrame(arr)
    assert (df.dtypes == arr.dtype).all()

    result = df.sum(skipna=False)
    expected = Series([pd.Timedelta(seconds=12), pd.NaT], dtype="m8[s]")
    tm.assert_series_equal(result, expected)

    result = df.sum(axis=0, skipna=False)
    tm.assert_series_equal(result, expected)

    result = df.sum(axis=1, skipna=False)
    expected = Series(
        [
            pd.Timedelta(seconds=1),
            pd.Timedelta(seconds=5),
            pd.Timedelta(seconds=9),
            pd.NaT,
        ],
        dtype="m8[s]",
    )
    tm.assert_series_equal(result, expected)


def test_mixed_frame_with_integer_sum():
    # https://github.com/pandas-dev/pandas/issues/34520
    df = DataFrame([["a", 1]], columns=list("ab"))
    df = df.astype({"b": "Int64"})
    result = df.sum()
    expected = Series(["a", 1], index=["a", "b"])
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("numeric_only", [True, False, None])
@pytest.mark.parametrize("method", ["min", "max"])
def test_minmax_extensionarray(method, numeric_only):
    # https://github.com/pandas-dev/pandas/issues/32651
    int64_info = np.iinfo("int64")
    ser = Series([int64_info.max, None, int64_info.min], dtype=pd.Int64Dtype())
    df = DataFrame({"Int64": ser})
    result = getattr(df, method)(numeric_only=numeric_only)
    expected = Series(
        [getattr(int64_info, method)],
        dtype="Int64",
        index=Index(["Int64"]),
    )
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("ts_value", [Timestamp("2000-01-01"), pd.NaT])
def test_frame_mixed_numeric_object_with_timestamp(ts_value):
    # GH 13912
    df = DataFrame({"a": [1], "b": [1.1], "c": ["foo"], "d": [ts_value]})
    with pytest.raises(
        TypeError, match="does not support (operation|reduction)|Cannot perform"
    ):
        df.sum()


def test_prod_sum_min_count_mixed_object():
    # https://github.com/pandas-dev/pandas/issues/41074
    df = DataFrame([1, "a", True])

    result = df.prod(axis=0, min_count=1, numeric_only=False)
    expected = Series(["a"], dtype=object)
    tm.assert_series_equal(result, expected)

    msg = re.escape("unsupported operand type(s) for +: 'int' and 'str'")
    with pytest.raises(TypeError, match=msg):
        df.sum(axis=0, min_count=1, numeric_only=False)


@pytest.mark.parametrize("method", ["min", "max", "mean", "median", "skew", "kurt"])
@pytest.mark.parametrize("numeric_only", [True, False])
@pytest.mark.parametrize("dtype", ["float64", "Float64"])
def test_reduction_axis_none_returns_scalar(method, numeric_only, dtype):
    # GH#21597 As of 2.0, axis=None reduces over all axes.

    df = DataFrame(np.random.default_rng(2).standard_normal((4, 4)), dtype=dtype)

    result = getattr(df, method)(axis=None, numeric_only=numeric_only)
    np_arr = df.to_numpy(dtype=np.float64)
    if method in {"skew", "kurt"}:
        comp_mod = pytest.importorskip("scipy.stats")
        if method == "kurt":
            method = "kurtosis"
        expected = getattr(comp_mod, method)(np_arr, bias=False, axis=None)
        tm.assert_almost_equal(result, expected)
    else:
        expected = getattr(np, method)(np_arr, axis=None)
        assert result == expected


@pytest.mark.parametrize(
    "kernel",
    [
        "corr",
        "corrwith",
        "cov",
        "idxmax",
        "idxmin",
        "kurt",
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
    ],
)
def test_fails_on_non_numeric(kernel):
    # GH#46852
    df = DataFrame({"a": [1, 2, 3], "b": object})
    args = (df,) if kernel == "corrwith" else ()
    msg = "|".join(
        [
            "not allowed for this dtype",
            "argument must be a string or a number",
            "not supported between instances of",
            "unsupported operand type",
            "argument must be a string or a real number",
        ]
    )
    if kernel == "median":
        # slightly different message on different builds
        msg1 = (
            r"Cannot convert \[\[<class 'object'> <class 'object'> "
            r"<class 'object'>\]\] to numeric"
        )
        msg2 = (
            r"Cannot convert \[<class 'object'> <class 'object'> "
            r"<class 'object'>\] to numeric"
        )
        msg = "|".join([msg1, msg2])
    with pytest.raises(TypeError, match=msg):
        getattr(df, kernel)(*args)


@pytest.mark.parametrize(
    "method",
    [
        "all",
        "any",
        "count",
        "idxmax",
        "idxmin",
        "kurt",
        "kurtosis",
        "max",
        "mean",
        "median",
        "min",
        "nunique",
        "prod",
        "product",
        "sem",
        "skew",
        "std",
        "sum",
        "var",
    ],
)
@pytest.mark.parametrize("min_count", [0, 2])
def test_numeric_ea_axis_1(method, skipna, min_count, any_numeric_ea_dtype):
    # GH 54341
    df = DataFrame(
        {
            "a": Series([0, 1, 2, 3], dtype=any_numeric_ea_dtype),
            "b": Series([0, 1, pd.NA, 3], dtype=any_numeric_ea_dtype),
        },
    )
    expected_df = DataFrame(
        {
            "a": [0.0, 1.0, 2.0, 3.0],
            "b": [0.0, 1.0, np.nan, 3.0],
        },
    )
    if method in ("count", "nunique"):
        expected_dtype = "int64"
    elif method in ("all", "any"):
        expected_dtype = "boolean"
    elif method in (
        "kurt",
        "kurtosis",
        "mean",
        "median",
        "sem",
        "skew",
        "std",
        "var",
    ) and not any_numeric_ea_dtype.startswith("Float"):
        expected_dtype = "Float64"
    else:
        expected_dtype = any_numeric_ea_dtype

    kwargs = {}
    if method not in ("count", "nunique", "quantile"):
        kwargs["skipna"] = skipna
    if method in ("prod", "product", "sum"):
        kwargs["min_count"] = min_count

    warn = None
    msg = None
    if not skipna and method in ("idxmax", "idxmin"):
        warn = FutureWarning
        msg = f"The behavior of DataFrame.{method} with all-NA values"
    with tm.assert_produces_warning(warn, match=msg):
        result = getattr(df, method)(axis=1, **kwargs)
    with tm.assert_produces_warning(warn, match=msg):
        expected = getattr(expected_df, method)(axis=1, **kwargs)
    if method not in ("idxmax", "idxmin"):
        expected = expected.astype(expected_dtype)
    tm.assert_series_equal(result, expected)
