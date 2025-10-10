import numpy as np
import pytest

from pandas.compat import WARNING_CHECK_DISABLED

from pandas import (
    NA,
    ArrowDtype,
    DataFrame,
    Interval,
    NaT,
    Series,
    Timestamp,
    interval_range,
    option_context,
)
import pandas._testing as tm
from pandas.tests.copy_view.util import get_array


@pytest.mark.parametrize("method", ["pad", "nearest", "linear"])
def test_interpolate_no_op(using_copy_on_write, method):
    df = DataFrame({"a": [1, 2]})
    df_orig = df.copy()

    warn = None
    if method == "pad":
        warn = FutureWarning
    msg = "DataFrame.interpolate with method=pad is deprecated"
    with tm.assert_produces_warning(warn, match=msg):
        result = df.interpolate(method=method)

    if using_copy_on_write:
        assert np.shares_memory(get_array(result, "a"), get_array(df, "a"))
    else:
        assert not np.shares_memory(get_array(result, "a"), get_array(df, "a"))

    result.iloc[0, 0] = 100

    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "a"), get_array(df, "a"))
    tm.assert_frame_equal(df, df_orig)


@pytest.mark.parametrize("func", ["ffill", "bfill"])
def test_interp_fill_functions(using_copy_on_write, func):
    # Check that these takes the same code paths as interpolate
    df = DataFrame({"a": [1, 2]})
    df_orig = df.copy()

    result = getattr(df, func)()

    if using_copy_on_write:
        assert np.shares_memory(get_array(result, "a"), get_array(df, "a"))
    else:
        assert not np.shares_memory(get_array(result, "a"), get_array(df, "a"))

    result.iloc[0, 0] = 100

    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "a"), get_array(df, "a"))
    tm.assert_frame_equal(df, df_orig)


@pytest.mark.parametrize("func", ["ffill", "bfill"])
@pytest.mark.parametrize(
    "vals", [[1, np.nan, 2], [Timestamp("2019-12-31"), NaT, Timestamp("2020-12-31")]]
)
def test_interpolate_triggers_copy(using_copy_on_write, vals, func):
    df = DataFrame({"a": vals})
    result = getattr(df, func)()

    assert not np.shares_memory(get_array(result, "a"), get_array(df, "a"))
    if using_copy_on_write:
        # Check that we don't have references when triggering a copy
        assert result._mgr._has_no_reference(0)


@pytest.mark.parametrize(
    "vals", [[1, np.nan, 2], [Timestamp("2019-12-31"), NaT, Timestamp("2020-12-31")]]
)
def test_interpolate_inplace_no_reference_no_copy(using_copy_on_write, vals):
    df = DataFrame({"a": vals})
    arr = get_array(df, "a")
    df.interpolate(method="linear", inplace=True)

    assert np.shares_memory(arr, get_array(df, "a"))
    if using_copy_on_write:
        # Check that we don't have references when triggering a copy
        assert df._mgr._has_no_reference(0)


@pytest.mark.parametrize(
    "vals", [[1, np.nan, 2], [Timestamp("2019-12-31"), NaT, Timestamp("2020-12-31")]]
)
def test_interpolate_inplace_with_refs(using_copy_on_write, vals, warn_copy_on_write):
    df = DataFrame({"a": [1, np.nan, 2]})
    df_orig = df.copy()
    arr = get_array(df, "a")
    view = df[:]
    with tm.assert_cow_warning(warn_copy_on_write):
        df.interpolate(method="linear", inplace=True)

    if using_copy_on_write:
        # Check that copy was triggered in interpolate and that we don't
        # have any references left
        assert not np.shares_memory(arr, get_array(df, "a"))
        tm.assert_frame_equal(df_orig, view)
        assert df._mgr._has_no_reference(0)
        assert view._mgr._has_no_reference(0)
    else:
        assert np.shares_memory(arr, get_array(df, "a"))


@pytest.mark.parametrize("func", ["ffill", "bfill"])
@pytest.mark.parametrize("dtype", ["float64", "Float64"])
def test_interp_fill_functions_inplace(
    using_copy_on_write, func, warn_copy_on_write, dtype
):
    # Check that these takes the same code paths as interpolate
    df = DataFrame({"a": [1, np.nan, 2]}, dtype=dtype)
    df_orig = df.copy()
    arr = get_array(df, "a")
    view = df[:]

    with tm.assert_cow_warning(warn_copy_on_write and dtype == "float64"):
        getattr(df, func)(inplace=True)

    if using_copy_on_write:
        # Check that copy was triggered in interpolate and that we don't
        # have any references left
        assert not np.shares_memory(arr, get_array(df, "a"))
        tm.assert_frame_equal(df_orig, view)
        assert df._mgr._has_no_reference(0)
        assert view._mgr._has_no_reference(0)
    else:
        assert np.shares_memory(arr, get_array(df, "a")) is (dtype == "float64")


def test_interpolate_cannot_with_object_dtype(using_copy_on_write):
    df = DataFrame({"a": ["a", np.nan, "c"], "b": 1})
    df["a"] = df["a"].astype(object)
    df_orig = df.copy()

    msg = "DataFrame.interpolate with object dtype"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = df.interpolate(method="linear")

    if using_copy_on_write:
        assert np.shares_memory(get_array(result, "a"), get_array(df, "a"))
    else:
        assert not np.shares_memory(get_array(result, "a"), get_array(df, "a"))

    result.iloc[0, 0] = Timestamp("2021-12-31")

    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "a"), get_array(df, "a"))
    tm.assert_frame_equal(df, df_orig)


def test_interpolate_object_convert_no_op(using_copy_on_write, using_infer_string):
    df = DataFrame({"a": ["a", "b", "c"], "b": 1})
    df["a"] = df["a"].astype(object)
    arr_a = get_array(df, "a")
    msg = "DataFrame.interpolate with method=pad is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        df.interpolate(method="pad", inplace=True)

    # Now CoW makes a copy, it should not!
    if using_copy_on_write and not using_infer_string:
        assert df._mgr._has_no_reference(0)
        assert np.shares_memory(arr_a, get_array(df, "a"))


def test_interpolate_object_convert_copies(using_copy_on_write):
    df = DataFrame({"a": Series([1, 2], dtype=object), "b": 1})
    arr_a = get_array(df, "a")
    msg = "DataFrame.interpolate with method=pad is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        df.interpolate(method="pad", inplace=True)

    if using_copy_on_write:
        assert df._mgr._has_no_reference(0)
        assert not np.shares_memory(arr_a, get_array(df, "a"))


def test_interpolate_downcast(using_copy_on_write):
    df = DataFrame({"a": [1, np.nan, 2.5], "b": 1})
    arr_a = get_array(df, "a")
    msg = "DataFrame.interpolate with method=pad is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        df.interpolate(method="pad", inplace=True, downcast="infer")

    if using_copy_on_write:
        assert df._mgr._has_no_reference(0)
    assert np.shares_memory(arr_a, get_array(df, "a"))


def test_interpolate_downcast_reference_triggers_copy(using_copy_on_write):
    df = DataFrame({"a": [1, np.nan, 2.5], "b": 1})
    df_orig = df.copy()
    arr_a = get_array(df, "a")
    view = df[:]
    msg = "DataFrame.interpolate with method=pad is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        df.interpolate(method="pad", inplace=True, downcast="infer")

    if using_copy_on_write:
        assert df._mgr._has_no_reference(0)
        assert not np.shares_memory(arr_a, get_array(df, "a"))
        tm.assert_frame_equal(df_orig, view)
    else:
        tm.assert_frame_equal(df, view)


def test_fillna(using_copy_on_write):
    df = DataFrame({"a": [1.5, np.nan], "b": 1})
    df_orig = df.copy()

    df2 = df.fillna(5.5)
    if using_copy_on_write:
        assert np.shares_memory(get_array(df, "b"), get_array(df2, "b"))
    else:
        assert not np.shares_memory(get_array(df, "b"), get_array(df2, "b"))

    df2.iloc[0, 1] = 100
    tm.assert_frame_equal(df_orig, df)


def test_fillna_dict(using_copy_on_write):
    df = DataFrame({"a": [1.5, np.nan], "b": 1})
    df_orig = df.copy()

    df2 = df.fillna({"a": 100.5})
    if using_copy_on_write:
        assert np.shares_memory(get_array(df, "b"), get_array(df2, "b"))
        assert not np.shares_memory(get_array(df, "a"), get_array(df2, "a"))
    else:
        assert not np.shares_memory(get_array(df, "b"), get_array(df2, "b"))

    df2.iloc[0, 1] = 100
    tm.assert_frame_equal(df_orig, df)


@pytest.mark.parametrize("downcast", [None, False])
def test_fillna_inplace(using_copy_on_write, downcast):
    df = DataFrame({"a": [1.5, np.nan], "b": 1})
    arr_a = get_array(df, "a")
    arr_b = get_array(df, "b")

    msg = "The 'downcast' keyword in fillna is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        df.fillna(5.5, inplace=True, downcast=downcast)
    assert np.shares_memory(get_array(df, "a"), arr_a)
    assert np.shares_memory(get_array(df, "b"), arr_b)
    if using_copy_on_write:
        assert df._mgr._has_no_reference(0)
        assert df._mgr._has_no_reference(1)


def test_fillna_inplace_reference(using_copy_on_write, warn_copy_on_write):
    df = DataFrame({"a": [1.5, np.nan], "b": 1})
    df_orig = df.copy()
    arr_a = get_array(df, "a")
    arr_b = get_array(df, "b")
    view = df[:]

    with tm.assert_cow_warning(warn_copy_on_write):
        df.fillna(5.5, inplace=True)
    if using_copy_on_write:
        assert not np.shares_memory(get_array(df, "a"), arr_a)
        assert np.shares_memory(get_array(df, "b"), arr_b)
        assert view._mgr._has_no_reference(0)
        assert df._mgr._has_no_reference(0)
        tm.assert_frame_equal(view, df_orig)
    else:
        assert np.shares_memory(get_array(df, "a"), arr_a)
        assert np.shares_memory(get_array(df, "b"), arr_b)
    expected = DataFrame({"a": [1.5, 5.5], "b": 1})
    tm.assert_frame_equal(df, expected)


def test_fillna_interval_inplace_reference(using_copy_on_write, warn_copy_on_write):
    # Set dtype explicitly to avoid implicit cast when setting nan
    ser = Series(
        interval_range(start=0, end=5), name="a", dtype="interval[float64, right]"
    )
    ser.iloc[1] = np.nan

    ser_orig = ser.copy()
    view = ser[:]
    with tm.assert_cow_warning(warn_copy_on_write):
        ser.fillna(value=Interval(left=0, right=5), inplace=True)

    if using_copy_on_write:
        assert not np.shares_memory(
            get_array(ser, "a").left.values, get_array(view, "a").left.values
        )
        tm.assert_series_equal(view, ser_orig)
    else:
        assert np.shares_memory(
            get_array(ser, "a").left.values, get_array(view, "a").left.values
        )


def test_fillna_series_empty_arg(using_copy_on_write):
    ser = Series([1, np.nan, 2])
    ser_orig = ser.copy()
    result = ser.fillna({})

    if using_copy_on_write:
        assert np.shares_memory(get_array(ser), get_array(result))
    else:
        assert not np.shares_memory(get_array(ser), get_array(result))

    ser.iloc[0] = 100.5
    tm.assert_series_equal(ser_orig, result)


def test_fillna_series_empty_arg_inplace(using_copy_on_write):
    ser = Series([1, np.nan, 2])
    arr = get_array(ser)
    ser.fillna({}, inplace=True)

    assert np.shares_memory(get_array(ser), arr)
    if using_copy_on_write:
        assert ser._mgr._has_no_reference(0)


def test_fillna_ea_noop_shares_memory(
    using_copy_on_write, any_numeric_ea_and_arrow_dtype
):
    df = DataFrame({"a": [1, NA, 3], "b": 1}, dtype=any_numeric_ea_and_arrow_dtype)
    df_orig = df.copy()
    df2 = df.fillna(100)

    assert not np.shares_memory(get_array(df, "a"), get_array(df2, "a"))

    if using_copy_on_write:
        assert np.shares_memory(get_array(df, "b"), get_array(df2, "b"))
        assert not df2._mgr._has_no_reference(1)
    elif isinstance(df.dtypes.iloc[0], ArrowDtype):
        # arrow is immutable, so no-ops do not need to copy underlying array
        assert np.shares_memory(get_array(df, "b"), get_array(df2, "b"))
    else:
        assert not np.shares_memory(get_array(df, "b"), get_array(df2, "b"))

    tm.assert_frame_equal(df_orig, df)

    df2.iloc[0, 1] = 100
    if using_copy_on_write:
        assert not np.shares_memory(get_array(df, "b"), get_array(df2, "b"))
        assert df2._mgr._has_no_reference(1)
        assert df._mgr._has_no_reference(1)
    tm.assert_frame_equal(df_orig, df)


def test_fillna_inplace_ea_noop_shares_memory(
    using_copy_on_write, warn_copy_on_write, any_numeric_ea_and_arrow_dtype
):
    df = DataFrame({"a": [1, NA, 3], "b": 1}, dtype=any_numeric_ea_and_arrow_dtype)
    df_orig = df.copy()
    view = df[:]
    with tm.assert_cow_warning(warn_copy_on_write):
        df.fillna(100, inplace=True)

    if isinstance(df["a"].dtype, ArrowDtype) or using_copy_on_write:
        assert not np.shares_memory(get_array(df, "a"), get_array(view, "a"))
    else:
        # MaskedArray can actually respect inplace=True
        assert np.shares_memory(get_array(df, "a"), get_array(view, "a"))

    assert np.shares_memory(get_array(df, "b"), get_array(view, "b"))
    if using_copy_on_write:
        assert not df._mgr._has_no_reference(1)
        assert not view._mgr._has_no_reference(1)

    with tm.assert_cow_warning(
        warn_copy_on_write and "pyarrow" not in any_numeric_ea_and_arrow_dtype
    ):
        df.iloc[0, 1] = 100
    if isinstance(df["a"].dtype, ArrowDtype) or using_copy_on_write:
        tm.assert_frame_equal(df_orig, view)
    else:
        # we actually have a view
        tm.assert_frame_equal(df, view)


def test_fillna_chained_assignment(using_copy_on_write):
    df = DataFrame({"a": [1, np.nan, 2], "b": 1})
    df_orig = df.copy()
    if using_copy_on_write:
        with tm.raises_chained_assignment_error():
            df["a"].fillna(100, inplace=True)
        tm.assert_frame_equal(df, df_orig)

        with tm.raises_chained_assignment_error():
            df[["a"]].fillna(100, inplace=True)
        tm.assert_frame_equal(df, df_orig)
    else:
        with tm.assert_produces_warning(None):
            with option_context("mode.chained_assignment", None):
                df[["a"]].fillna(100, inplace=True)

        with tm.assert_produces_warning(None):
            with option_context("mode.chained_assignment", None):
                df[df.a > 5].fillna(100, inplace=True)

        with tm.assert_produces_warning(
            FutureWarning if not WARNING_CHECK_DISABLED else None,
            match="inplace method",
        ):
            df["a"].fillna(100, inplace=True)


@pytest.mark.parametrize("func", ["interpolate", "ffill", "bfill"])
def test_interpolate_chained_assignment(using_copy_on_write, func):
    df = DataFrame({"a": [1, np.nan, 2], "b": 1})
    df_orig = df.copy()
    if using_copy_on_write:
        with tm.raises_chained_assignment_error():
            getattr(df["a"], func)(inplace=True)
        tm.assert_frame_equal(df, df_orig)

        with tm.raises_chained_assignment_error():
            getattr(df[["a"]], func)(inplace=True)
        tm.assert_frame_equal(df, df_orig)
    else:
        with tm.assert_produces_warning(
            FutureWarning if not WARNING_CHECK_DISABLED else None,
            match="inplace method",
        ):
            getattr(df["a"], func)(inplace=True)

        with tm.assert_produces_warning(None):
            with option_context("mode.chained_assignment", None):
                getattr(df[["a"]], func)(inplace=True)

        with tm.assert_produces_warning(None):
            with option_context("mode.chained_assignment", None):
                getattr(df[df["a"] > 1], func)(inplace=True)
