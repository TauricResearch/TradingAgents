import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    MultiIndex,
    Series,
    concat,
    date_range,
    timedelta_range,
)
import pandas._testing as tm
from pandas.tests.apply.common import series_transform_kernels


@pytest.fixture(params=[False, "compat"])
def by_row(request):
    return request.param


def test_series_map_box_timedelta(by_row):
    # GH#11349
    ser = Series(timedelta_range("1 day 1 s", periods=3, freq="h"))

    def f(x):
        return x.total_seconds() if by_row else x.dt.total_seconds()

    result = ser.apply(f, by_row=by_row)

    expected = ser.map(lambda x: x.total_seconds())
    tm.assert_series_equal(result, expected)

    expected = Series([86401.0, 90001.0, 93601.0])
    tm.assert_series_equal(result, expected)


def test_apply(datetime_series, by_row):
    result = datetime_series.apply(np.sqrt, by_row=by_row)
    with np.errstate(all="ignore"):
        expected = np.sqrt(datetime_series)
    tm.assert_series_equal(result, expected)

    # element-wise apply (ufunc)
    result = datetime_series.apply(np.exp, by_row=by_row)
    expected = np.exp(datetime_series)
    tm.assert_series_equal(result, expected)

    # empty series
    s = Series(dtype=object, name="foo", index=Index([], name="bar"))
    rs = s.apply(lambda x: x, by_row=by_row)
    tm.assert_series_equal(s, rs)

    # check all metadata (GH 9322)
    assert s is not rs
    assert s.index is rs.index
    assert s.dtype == rs.dtype
    assert s.name == rs.name

    # index but no data
    s = Series(index=[1, 2, 3], dtype=np.float64)
    rs = s.apply(lambda x: x, by_row=by_row)
    tm.assert_series_equal(s, rs)


def test_apply_map_same_length_inference_bug():
    s = Series([1, 2])

    def f(x):
        return (x, x + 1)

    result = s.apply(f, by_row="compat")
    expected = s.map(f)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("convert_dtype", [True, False])
def test_apply_convert_dtype_deprecated(convert_dtype):
    ser = Series(np.random.default_rng(2).standard_normal(10))

    def func(x):
        return x if x > 0 else np.nan

    with tm.assert_produces_warning(FutureWarning):
        ser.apply(func, convert_dtype=convert_dtype, by_row="compat")


def test_apply_args():
    s = Series(["foo,bar"])

    result = s.apply(str.split, args=(",",))
    assert result[0] == ["foo", "bar"]
    assert isinstance(result[0], list)


@pytest.mark.parametrize(
    "args, kwargs, increment",
    [((), {}, 0), ((), {"a": 1}, 1), ((2, 3), {}, 32), ((1,), {"c": 2}, 201)],
)
def test_agg_args(args, kwargs, increment):
    # GH 43357
    def f(x, a=0, b=0, c=0):
        return x + a + 10 * b + 100 * c

    s = Series([1, 2])
    msg = (
        "in Series.agg cannot aggregate and has been deprecated. "
        "Use Series.transform to keep behavior unchanged."
    )
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = s.agg(f, 0, *args, **kwargs)
    expected = s + increment
    tm.assert_series_equal(result, expected)


def test_agg_mapping_func_deprecated():
    # GH 53325
    s = Series([1, 2, 3])

    def foo1(x, a=1, c=0):
        return x + a + c

    def foo2(x, b=2, c=0):
        return x + b + c

    msg = "using .+ in Series.agg cannot aggregate and"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        s.agg(foo1, 0, 3, c=4)
    with tm.assert_produces_warning(FutureWarning, match=msg):
        s.agg([foo1, foo2], 0, 3, c=4)
    with tm.assert_produces_warning(FutureWarning, match=msg):
        s.agg({"a": foo1, "b": foo2}, 0, 3, c=4)


def test_series_apply_map_box_timestamps(by_row):
    # GH#2689, GH#2627
    ser = Series(date_range("1/1/2000", periods=10))

    def func(x):
        return (x.hour, x.day, x.month)

    if not by_row:
        msg = "Series' object has no attribute 'hour'"
        with pytest.raises(AttributeError, match=msg):
            ser.apply(func, by_row=by_row)
        return

    result = ser.apply(func, by_row=by_row)
    expected = ser.map(func)
    tm.assert_series_equal(result, expected)


def test_apply_box_dt64():
    # ufunc will not be boxed. Same test cases as the test_map_box
    vals = [pd.Timestamp("2011-01-01"), pd.Timestamp("2011-01-02")]
    ser = Series(vals, dtype="M8[ns]")
    assert ser.dtype == "datetime64[ns]"
    # boxed value must be Timestamp instance
    res = ser.apply(lambda x: f"{type(x).__name__}_{x.day}_{x.tz}", by_row="compat")
    exp = Series(["Timestamp_1_None", "Timestamp_2_None"])
    tm.assert_series_equal(res, exp)


def test_apply_box_dt64tz():
    vals = [
        pd.Timestamp("2011-01-01", tz="US/Eastern"),
        pd.Timestamp("2011-01-02", tz="US/Eastern"),
    ]
    ser = Series(vals, dtype="M8[ns, US/Eastern]")
    assert ser.dtype == "datetime64[ns, US/Eastern]"
    res = ser.apply(lambda x: f"{type(x).__name__}_{x.day}_{x.tz}", by_row="compat")
    exp = Series(["Timestamp_1_US/Eastern", "Timestamp_2_US/Eastern"])
    tm.assert_series_equal(res, exp)


def test_apply_box_td64():
    # timedelta
    vals = [pd.Timedelta("1 days"), pd.Timedelta("2 days")]
    ser = Series(vals)
    assert ser.dtype == "timedelta64[ns]"
    res = ser.apply(lambda x: f"{type(x).__name__}_{x.days}", by_row="compat")
    exp = Series(["Timedelta_1", "Timedelta_2"])
    tm.assert_series_equal(res, exp)


def test_apply_box_period():
    # period
    vals = [pd.Period("2011-01-01", freq="M"), pd.Period("2011-01-02", freq="M")]
    ser = Series(vals)
    assert ser.dtype == "Period[M]"
    res = ser.apply(lambda x: f"{type(x).__name__}_{x.freqstr}", by_row="compat")
    exp = Series(["Period_M", "Period_M"])
    tm.assert_series_equal(res, exp)


def test_apply_datetimetz(by_row):
    values = date_range("2011-01-01", "2011-01-02", freq="h").tz_localize("Asia/Tokyo")
    s = Series(values, name="XX")

    result = s.apply(lambda x: x + pd.offsets.Day(), by_row=by_row)
    exp_values = date_range("2011-01-02", "2011-01-03", freq="h").tz_localize(
        "Asia/Tokyo"
    )
    exp = Series(exp_values, name="XX")
    tm.assert_series_equal(result, exp)

    result = s.apply(lambda x: x.hour if by_row else x.dt.hour, by_row=by_row)
    exp = Series(list(range(24)) + [0], name="XX", dtype="int64" if by_row else "int32")
    tm.assert_series_equal(result, exp)

    # not vectorized
    def f(x):
        return str(x.tz) if by_row else str(x.dt.tz)

    result = s.apply(f, by_row=by_row)
    if by_row:
        exp = Series(["Asia/Tokyo"] * 25, name="XX")
        tm.assert_series_equal(result, exp)
    else:
        assert result == "Asia/Tokyo"


def test_apply_categorical(by_row, using_infer_string):
    values = pd.Categorical(list("ABBABCD"), categories=list("DCBA"), ordered=True)
    ser = Series(values, name="XX", index=list("abcdefg"))

    if not by_row:
        msg = "Series' object has no attribute 'lower"
        with pytest.raises(AttributeError, match=msg):
            ser.apply(lambda x: x.lower(), by_row=by_row)
        assert ser.apply(lambda x: "A", by_row=by_row) == "A"
        return

    result = ser.apply(lambda x: x.lower(), by_row=by_row)

    # should be categorical dtype when the number of categories are
    # the same
    values = pd.Categorical(list("abbabcd"), categories=list("dcba"), ordered=True)
    exp = Series(values, name="XX", index=list("abcdefg"))
    tm.assert_series_equal(result, exp)
    tm.assert_categorical_equal(result.values, exp.values)

    result = ser.apply(lambda x: "A")
    exp = Series(["A"] * 7, name="XX", index=list("abcdefg"))
    tm.assert_series_equal(result, exp)
    assert result.dtype == object if not using_infer_string else "str"


@pytest.mark.parametrize("series", [["1-1", "1-1", np.nan], ["1-1", "1-2", np.nan]])
def test_apply_categorical_with_nan_values(series, by_row):
    # GH 20714 bug fixed in: GH 24275
    s = Series(series, dtype="category")
    if not by_row:
        msg = "'Series' object has no attribute 'split'"
        with pytest.raises(AttributeError, match=msg):
            s.apply(lambda x: x.split("-")[0], by_row=by_row)
        return

    result = s.apply(lambda x: x.split("-")[0], by_row=by_row)
    result = result.astype(object)
    expected = Series(["1", "1", np.nan], dtype="category")
    expected = expected.astype(object)
    tm.assert_series_equal(result, expected)


def test_apply_empty_integer_series_with_datetime_index(by_row):
    # GH 21245
    s = Series([], index=date_range(start="2018-01-01", periods=0), dtype=int)
    result = s.apply(lambda x: x, by_row=by_row)
    tm.assert_series_equal(result, s)


def test_apply_dataframe_iloc():
    uintDF = DataFrame(np.uint64([1, 2, 3, 4, 5]), columns=["Numbers"])
    indexDF = DataFrame([2, 3, 2, 1, 2], columns=["Indices"])

    def retrieve(targetRow, targetDF):
        val = targetDF["Numbers"].iloc[targetRow]
        return val

    result = indexDF["Indices"].apply(retrieve, args=(uintDF,))
    expected = Series([3, 4, 3, 2, 3], name="Indices", dtype="uint64")
    tm.assert_series_equal(result, expected)


def test_transform(string_series, by_row):
    # transforming functions

    with np.errstate(all="ignore"):
        f_sqrt = np.sqrt(string_series)
        f_abs = np.abs(string_series)

        # ufunc
        result = string_series.apply(np.sqrt, by_row=by_row)
        expected = f_sqrt.copy()
        tm.assert_series_equal(result, expected)

        # list-like
        result = string_series.apply([np.sqrt], by_row=by_row)
        expected = f_sqrt.to_frame().copy()
        expected.columns = ["sqrt"]
        tm.assert_frame_equal(result, expected)

        result = string_series.apply(["sqrt"], by_row=by_row)
        tm.assert_frame_equal(result, expected)

        # multiple items in list
        # these are in the order as if we are applying both functions per
        # series and then concatting
        expected = concat([f_sqrt, f_abs], axis=1)
        expected.columns = ["sqrt", "absolute"]
        result = string_series.apply([np.sqrt, np.abs], by_row=by_row)
        tm.assert_frame_equal(result, expected)

        # dict, provide renaming
        expected = concat([f_sqrt, f_abs], axis=1)
        expected.columns = ["foo", "bar"]
        expected = expected.unstack().rename("series")

        result = string_series.apply({"foo": np.sqrt, "bar": np.abs}, by_row=by_row)
        tm.assert_series_equal(result.reindex_like(expected), expected)


@pytest.mark.parametrize("op", series_transform_kernels)
def test_transform_partial_failure(op, request):
    # GH 35964
    if op in ("ffill", "bfill", "pad", "backfill", "shift"):
        request.applymarker(
            pytest.mark.xfail(reason=f"{op} is successful on any dtype")
        )

    # Using object makes most transform kernels fail
    ser = Series(3 * [object])

    if op in ("fillna", "ngroup"):
        error = ValueError
        msg = "Transform function failed"
    else:
        error = TypeError
        msg = "|".join(
            [
                "not supported between instances of 'type' and 'type'",
                "unsupported operand type",
            ]
        )

    with pytest.raises(error, match=msg):
        ser.transform([op, "shift"])

    with pytest.raises(error, match=msg):
        ser.transform({"A": op, "B": "shift"})

    with pytest.raises(error, match=msg):
        ser.transform({"A": [op], "B": ["shift"]})

    with pytest.raises(error, match=msg):
        ser.transform({"A": [op, "shift"], "B": [op]})


def test_transform_partial_failure_valueerror():
    # GH 40211
    def noop(x):
        return x

    def raising_op(_):
        raise ValueError

    ser = Series(3 * [object])
    msg = "Transform function failed"

    with pytest.raises(ValueError, match=msg):
        ser.transform([noop, raising_op])

    with pytest.raises(ValueError, match=msg):
        ser.transform({"A": raising_op, "B": noop})

    with pytest.raises(ValueError, match=msg):
        ser.transform({"A": [raising_op], "B": [noop]})

    with pytest.raises(ValueError, match=msg):
        ser.transform({"A": [noop, raising_op], "B": [noop]})


def test_demo():
    # demonstration tests
    s = Series(range(6), dtype="int64", name="series")

    result = s.agg(["min", "max"])
    expected = Series([0, 5], index=["min", "max"], name="series")
    tm.assert_series_equal(result, expected)

    result = s.agg({"foo": "min"})
    expected = Series([0], index=["foo"], name="series")
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("func", [str, lambda x: str(x)])
def test_apply_map_evaluate_lambdas_the_same(string_series, func, by_row):
    # test that we are evaluating row-by-row first if by_row="compat"
    # else vectorized evaluation
    result = string_series.apply(func, by_row=by_row)

    if by_row:
        expected = string_series.map(func)
        tm.assert_series_equal(result, expected)
    else:
        assert result == str(string_series)


def test_agg_evaluate_lambdas(string_series):
    # GH53325
    # in the future, the result will be a Series class.

    with tm.assert_produces_warning(FutureWarning):
        result = string_series.agg(lambda x: type(x))
    assert isinstance(result, Series) and len(result) == len(string_series)

    with tm.assert_produces_warning(FutureWarning):
        result = string_series.agg(type)
    assert isinstance(result, Series) and len(result) == len(string_series)


@pytest.mark.parametrize("op_name", ["agg", "apply"])
def test_with_nested_series(datetime_series, op_name):
    # GH 2316
    # .agg with a reducer and a transform, what to do
    msg = "cannot aggregate"
    warning = FutureWarning if op_name == "agg" else None
    with tm.assert_produces_warning(warning, match=msg):
        # GH52123
        result = getattr(datetime_series, op_name)(
            lambda x: Series([x, x**2], index=["x", "x^2"])
        )
    expected = DataFrame({"x": datetime_series, "x^2": datetime_series**2})
    tm.assert_frame_equal(result, expected)

    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = datetime_series.agg(lambda x: Series([x, x**2], index=["x", "x^2"]))
    tm.assert_frame_equal(result, expected)


def test_replicate_describe(string_series):
    # this also tests a result set that is all scalars
    expected = string_series.describe()
    result = string_series.apply(
        {
            "count": "count",
            "mean": "mean",
            "std": "std",
            "min": "min",
            "25%": lambda x: x.quantile(0.25),
            "50%": "median",
            "75%": lambda x: x.quantile(0.75),
            "max": "max",
        },
    )
    tm.assert_series_equal(result, expected)


def test_reduce(string_series):
    # reductions with named functions
    result = string_series.agg(["sum", "mean"])
    expected = Series(
        [string_series.sum(), string_series.mean()],
        ["sum", "mean"],
        name=string_series.name,
    )
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "how, kwds",
    [("agg", {}), ("apply", {"by_row": "compat"}), ("apply", {"by_row": False})],
)
def test_non_callable_aggregates(how, kwds):
    # test agg using non-callable series attributes
    # GH 39116 - expand to apply
    s = Series([1, 2, None])

    # Calling agg w/ just a string arg same as calling s.arg
    result = getattr(s, how)("size", **kwds)
    expected = s.size
    assert result == expected

    # test when mixed w/ callable reducers
    result = getattr(s, how)(["size", "count", "mean"], **kwds)
    expected = Series({"size": 3.0, "count": 2.0, "mean": 1.5})
    tm.assert_series_equal(result, expected)

    result = getattr(s, how)({"size": "size", "count": "count", "mean": "mean"}, **kwds)
    tm.assert_series_equal(result, expected)


def test_series_apply_no_suffix_index(by_row):
    # GH36189
    s = Series([4] * 3)
    result = s.apply(["sum", lambda x: x.sum(), lambda x: x.sum()], by_row=by_row)
    expected = Series([12, 12, 12], index=["sum", "<lambda>", "<lambda>"])

    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "dti,exp",
    [
        (
            Series([1, 2], index=pd.DatetimeIndex([0, 31536000000])),
            DataFrame(np.repeat([[1, 2]], 2, axis=0), dtype="int64"),
        ),
        (
            Series(
                np.arange(10, dtype=np.float64),
                index=date_range("2020-01-01", periods=10),
                name="ts",
            ),
            DataFrame(np.repeat([[1, 2]], 10, axis=0), dtype="int64"),
        ),
    ],
)
@pytest.mark.parametrize("aware", [True, False])
def test_apply_series_on_date_time_index_aware_series(dti, exp, aware):
    # GH 25959
    # Calling apply on a localized time series should not cause an error
    if aware:
        index = dti.tz_localize("UTC").index
    else:
        index = dti.index
    result = Series(index).apply(lambda x: Series([1, 2]))
    tm.assert_frame_equal(result, exp)


@pytest.mark.parametrize(
    "by_row, expected", [("compat", Series(np.ones(10), dtype="int64")), (False, 1)]
)
def test_apply_scalar_on_date_time_index_aware_series(by_row, expected):
    # GH 25959
    # Calling apply on a localized time series should not cause an error
    series = Series(
        np.arange(10, dtype=np.float64),
        index=date_range("2020-01-01", periods=10, tz="UTC"),
    )
    result = Series(series.index).apply(lambda x: 1, by_row=by_row)
    tm.assert_equal(result, expected)


def test_apply_to_timedelta(by_row):
    list_of_valid_strings = ["00:00:01", "00:00:02"]
    a = pd.to_timedelta(list_of_valid_strings)
    b = Series(list_of_valid_strings).apply(pd.to_timedelta, by_row=by_row)
    tm.assert_series_equal(Series(a), b)

    list_of_strings = ["00:00:01", np.nan, pd.NaT, pd.NaT]

    a = pd.to_timedelta(list_of_strings)
    ser = Series(list_of_strings)
    b = ser.apply(pd.to_timedelta, by_row=by_row)
    tm.assert_series_equal(Series(a), b)


@pytest.mark.parametrize(
    "ops, names",
    [
        ([np.sum], ["sum"]),
        ([np.sum, np.mean], ["sum", "mean"]),
        (np.array([np.sum]), ["sum"]),
        (np.array([np.sum, np.mean]), ["sum", "mean"]),
    ],
)
@pytest.mark.parametrize(
    "how, kwargs",
    [["agg", {}], ["apply", {"by_row": "compat"}], ["apply", {"by_row": False}]],
)
def test_apply_listlike_reducer(string_series, ops, names, how, kwargs):
    # GH 39140
    expected = Series({name: op(string_series) for name, op in zip(names, ops)})
    expected.name = "series"
    warn = FutureWarning if how == "agg" else None
    msg = f"using Series.[{'|'.join(names)}]"
    with tm.assert_produces_warning(warn, match=msg):
        result = getattr(string_series, how)(ops, **kwargs)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "ops",
    [
        {"A": np.sum},
        {"A": np.sum, "B": np.mean},
        Series({"A": np.sum}),
        Series({"A": np.sum, "B": np.mean}),
    ],
)
@pytest.mark.parametrize(
    "how, kwargs",
    [["agg", {}], ["apply", {"by_row": "compat"}], ["apply", {"by_row": False}]],
)
def test_apply_dictlike_reducer(string_series, ops, how, kwargs, by_row):
    # GH 39140
    expected = Series({name: op(string_series) for name, op in ops.items()})
    expected.name = string_series.name
    warn = FutureWarning if how == "agg" else None
    msg = "using Series.[sum|mean]"
    with tm.assert_produces_warning(warn, match=msg):
        result = getattr(string_series, how)(ops, **kwargs)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "ops, names",
    [
        ([np.sqrt], ["sqrt"]),
        ([np.abs, np.sqrt], ["absolute", "sqrt"]),
        (np.array([np.sqrt]), ["sqrt"]),
        (np.array([np.abs, np.sqrt]), ["absolute", "sqrt"]),
    ],
)
def test_apply_listlike_transformer(string_series, ops, names, by_row):
    # GH 39140
    with np.errstate(all="ignore"):
        expected = concat([op(string_series) for op in ops], axis=1)
        expected.columns = names
        result = string_series.apply(ops, by_row=by_row)
        tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "ops, expected",
    [
        ([lambda x: x], DataFrame({"<lambda>": [1, 2, 3]})),
        ([lambda x: x.sum()], Series([6], index=["<lambda>"])),
    ],
)
def test_apply_listlike_lambda(ops, expected, by_row):
    # GH53400
    ser = Series([1, 2, 3])
    result = ser.apply(ops, by_row=by_row)
    tm.assert_equal(result, expected)


@pytest.mark.parametrize(
    "ops",
    [
        {"A": np.sqrt},
        {"A": np.sqrt, "B": np.exp},
        Series({"A": np.sqrt}),
        Series({"A": np.sqrt, "B": np.exp}),
    ],
)
def test_apply_dictlike_transformer(string_series, ops, by_row):
    # GH 39140
    with np.errstate(all="ignore"):
        expected = concat({name: op(string_series) for name, op in ops.items()})
        expected.name = string_series.name
        result = string_series.apply(ops, by_row=by_row)
        tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "ops, expected",
    [
        (
            {"a": lambda x: x},
            Series([1, 2, 3], index=MultiIndex.from_arrays([["a"] * 3, range(3)])),
        ),
        ({"a": lambda x: x.sum()}, Series([6], index=["a"])),
    ],
)
def test_apply_dictlike_lambda(ops, by_row, expected):
    # GH53400
    ser = Series([1, 2, 3])
    result = ser.apply(ops, by_row=by_row)
    tm.assert_equal(result, expected)


def test_apply_retains_column_name(by_row):
    # GH 16380
    df = DataFrame({"x": range(3)}, Index(range(3), name="x"))
    result = df.x.apply(lambda x: Series(range(x + 1), Index(range(x + 1), name="y")))
    expected = DataFrame(
        [[0.0, np.nan, np.nan], [0.0, 1.0, np.nan], [0.0, 1.0, 2.0]],
        columns=Index(range(3), name="y"),
        index=Index(range(3), name="x"),
    )
    tm.assert_frame_equal(result, expected)


def test_apply_type():
    # GH 46719
    s = Series([3, "string", float], index=["a", "b", "c"])
    result = s.apply(type)
    expected = Series([int, str, type], index=["a", "b", "c"])
    tm.assert_series_equal(result, expected)


def test_series_apply_unpack_nested_data():
    # GH#55189
    ser = Series([[1, 2, 3], [4, 5, 6, 7]])
    result = ser.apply(lambda x: Series(x))
    expected = DataFrame({0: [1.0, 4.0], 1: [2.0, 5.0], 2: [3.0, 6.0], 3: [np.nan, 7]})
    tm.assert_frame_equal(result, expected)
