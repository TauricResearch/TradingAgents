import pickle

import numpy as np
import pytest

from pandas.compat import HAS_PYARROW
from pandas.compat.pyarrow import pa_version_under12p0
import pandas.util._test_decorators as td

import pandas as pd
from pandas import (
    DataFrame,
    Series,
    Timestamp,
    date_range,
)
import pandas._testing as tm
from pandas.tests.copy_view.util import get_array


def test_astype_single_dtype(using_copy_on_write):
    df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": 1.5})
    df_orig = df.copy()
    df2 = df.astype("float64")

    if using_copy_on_write:
        assert np.shares_memory(get_array(df2, "c"), get_array(df, "c"))
        assert not np.shares_memory(get_array(df2, "a"), get_array(df, "a"))
    else:
        assert not np.shares_memory(get_array(df2, "c"), get_array(df, "c"))
        assert not np.shares_memory(get_array(df2, "a"), get_array(df, "a"))

    # mutating df2 triggers a copy-on-write for that column/block
    df2.iloc[0, 2] = 5.5
    if using_copy_on_write:
        assert not np.shares_memory(get_array(df2, "c"), get_array(df, "c"))
    tm.assert_frame_equal(df, df_orig)

    # mutating parent also doesn't update result
    df2 = df.astype("float64")
    df.iloc[0, 2] = 5.5
    tm.assert_frame_equal(df2, df_orig.astype("float64"))


@pytest.mark.parametrize("dtype", ["int64", "Int64"])
@pytest.mark.parametrize("new_dtype", ["int64", "Int64", "int64[pyarrow]"])
def test_astype_avoids_copy(using_copy_on_write, dtype, new_dtype):
    if new_dtype == "int64[pyarrow]":
        pytest.importorskip("pyarrow")
    df = DataFrame({"a": [1, 2, 3]}, dtype=dtype)
    df_orig = df.copy()
    df2 = df.astype(new_dtype)

    if using_copy_on_write:
        assert np.shares_memory(get_array(df2, "a"), get_array(df, "a"))
    else:
        assert not np.shares_memory(get_array(df2, "a"), get_array(df, "a"))

    # mutating df2 triggers a copy-on-write for that column/block
    df2.iloc[0, 0] = 10
    if using_copy_on_write:
        assert not np.shares_memory(get_array(df2, "a"), get_array(df, "a"))
    tm.assert_frame_equal(df, df_orig)

    # mutating parent also doesn't update result
    df2 = df.astype(new_dtype)
    df.iloc[0, 0] = 100
    tm.assert_frame_equal(df2, df_orig.astype(new_dtype))


@pytest.mark.parametrize("dtype", ["float64", "int32", "Int32", "int32[pyarrow]"])
def test_astype_different_target_dtype(using_copy_on_write, dtype):
    if dtype == "int32[pyarrow]":
        pytest.importorskip("pyarrow")
    df = DataFrame({"a": [1, 2, 3]})
    df_orig = df.copy()
    df2 = df.astype(dtype)

    assert not np.shares_memory(get_array(df2, "a"), get_array(df, "a"))
    if using_copy_on_write:
        assert df2._mgr._has_no_reference(0)

    df2.iloc[0, 0] = 5
    tm.assert_frame_equal(df, df_orig)

    # mutating parent also doesn't update result
    df2 = df.astype(dtype)
    df.iloc[0, 0] = 100
    tm.assert_frame_equal(df2, df_orig.astype(dtype))


@td.skip_array_manager_invalid_test
def test_astype_numpy_to_ea():
    ser = Series([1, 2, 3])
    with pd.option_context("mode.copy_on_write", True):
        result = ser.astype("Int64")
    assert np.shares_memory(get_array(ser), get_array(result))


@pytest.mark.parametrize(
    "dtype, new_dtype", [("object", "string"), ("string", "object")]
)
def test_astype_string_and_object(using_copy_on_write, dtype, new_dtype):
    df = DataFrame({"a": ["a", "b", "c"]}, dtype=dtype)
    df_orig = df.copy()
    df2 = df.astype(new_dtype)

    if using_copy_on_write:
        assert np.shares_memory(get_array(df2, "a"), get_array(df, "a"))
    else:
        assert not np.shares_memory(get_array(df2, "a"), get_array(df, "a"))

    df2.iloc[0, 0] = "x"
    tm.assert_frame_equal(df, df_orig)


@pytest.mark.parametrize(
    "dtype, new_dtype", [("object", "string"), ("string", "object")]
)
def test_astype_string_and_object_update_original(
    using_copy_on_write, dtype, new_dtype
):
    df = DataFrame({"a": ["a", "b", "c"]}, dtype=dtype)
    df2 = df.astype(new_dtype)
    df_orig = df2.copy()

    if using_copy_on_write:
        assert np.shares_memory(get_array(df2, "a"), get_array(df, "a"))
    else:
        assert not np.shares_memory(get_array(df2, "a"), get_array(df, "a"))

    df.iloc[0, 0] = "x"
    tm.assert_frame_equal(df2, df_orig)


def test_astype_str_copy_on_pickle_roundrip():
    # TODO(infer_string) this test can be removed after 3.0 (once str is the default)
    # https://github.com/pandas-dev/pandas/issues/54654
    # ensure_string_array may alter array inplace
    base = Series(np.array([(1, 2), None, 1], dtype="object"))
    base_copy = pickle.loads(pickle.dumps(base))
    base_copy.astype(str)
    tm.assert_series_equal(base, base_copy)


def test_astype_string_copy_on_pickle_roundrip(any_string_dtype):
    # https://github.com/pandas-dev/pandas/issues/54654
    # ensure_string_array may alter array inplace
    base = Series(np.array([(1, 2), None, 1], dtype="object"))
    base_copy = pickle.loads(pickle.dumps(base))
    base_copy.astype(any_string_dtype)
    tm.assert_series_equal(base, base_copy)


def test_astype_string_read_only_on_pickle_roundrip(any_string_dtype):
    # https://github.com/pandas-dev/pandas/issues/54654
    # ensure_string_array may alter read-only array inplace
    base = Series(np.array([(1, 2), None, 1], dtype="object"))
    base_copy = pickle.loads(pickle.dumps(base))
    base_copy._values.flags.writeable = False
    base_copy.astype(any_string_dtype)
    tm.assert_series_equal(base, base_copy)


def test_astype_dict_dtypes(using_copy_on_write):
    df = DataFrame(
        {"a": [1, 2, 3], "b": [4, 5, 6], "c": Series([1.5, 1.5, 1.5], dtype="float64")}
    )
    df_orig = df.copy()
    df2 = df.astype({"a": "float64", "c": "float64"})

    if using_copy_on_write:
        assert np.shares_memory(get_array(df2, "c"), get_array(df, "c"))
        assert np.shares_memory(get_array(df2, "b"), get_array(df, "b"))
        assert not np.shares_memory(get_array(df2, "a"), get_array(df, "a"))
    else:
        assert not np.shares_memory(get_array(df2, "c"), get_array(df, "c"))
        assert not np.shares_memory(get_array(df2, "b"), get_array(df, "b"))
        assert not np.shares_memory(get_array(df2, "a"), get_array(df, "a"))

    # mutating df2 triggers a copy-on-write for that column/block
    df2.iloc[0, 2] = 5.5
    if using_copy_on_write:
        assert not np.shares_memory(get_array(df2, "c"), get_array(df, "c"))

    df2.iloc[0, 1] = 10
    if using_copy_on_write:
        assert not np.shares_memory(get_array(df2, "b"), get_array(df, "b"))
    tm.assert_frame_equal(df, df_orig)


def test_astype_different_datetime_resos(using_copy_on_write):
    df = DataFrame({"a": date_range("2019-12-31", periods=2, freq="D")})
    result = df.astype("datetime64[ms]")

    assert not np.shares_memory(get_array(df, "a"), get_array(result, "a"))
    if using_copy_on_write:
        assert result._mgr._has_no_reference(0)


def test_astype_different_timezones(using_copy_on_write):
    df = DataFrame(
        {"a": date_range("2019-12-31", periods=5, freq="D", tz="US/Pacific")}
    )
    result = df.astype("datetime64[ns, Europe/Berlin]")
    if using_copy_on_write:
        assert not result._mgr._has_no_reference(0)
        assert np.shares_memory(get_array(df, "a"), get_array(result, "a"))


def test_astype_different_timezones_different_reso(using_copy_on_write):
    df = DataFrame(
        {"a": date_range("2019-12-31", periods=5, freq="D", tz="US/Pacific")}
    )
    result = df.astype("datetime64[ms, Europe/Berlin]")
    if using_copy_on_write:
        assert result._mgr._has_no_reference(0)
        assert not np.shares_memory(get_array(df, "a"), get_array(result, "a"))


def test_astype_arrow_timestamp(using_copy_on_write):
    pytest.importorskip("pyarrow")
    df = DataFrame(
        {
            "a": [
                Timestamp("2020-01-01 01:01:01.000001"),
                Timestamp("2020-01-01 01:01:01.000001"),
            ]
        },
        dtype="M8[ns]",
    )
    result = df.astype("timestamp[ns][pyarrow]")
    if using_copy_on_write:
        assert not result._mgr._has_no_reference(0)
        if pa_version_under12p0:
            assert not np.shares_memory(
                get_array(df, "a"), get_array(result, "a")._pa_array
            )
        else:
            assert np.shares_memory(
                get_array(df, "a"), get_array(result, "a")._pa_array
            )


def test_convert_dtypes_infer_objects(using_copy_on_write):
    ser = Series(["a", "b", "c"])
    ser_orig = ser.copy()
    result = ser.convert_dtypes(
        convert_integer=False,
        convert_boolean=False,
        convert_floating=False,
        convert_string=False,
    )

    if using_copy_on_write:
        assert tm.shares_memory(get_array(ser), get_array(result))
    else:
        assert not np.shares_memory(get_array(ser), get_array(result))

    result.iloc[0] = "x"
    tm.assert_series_equal(ser, ser_orig)


def test_convert_dtypes(using_copy_on_write, using_infer_string):
    df = DataFrame({"a": ["a", "b"], "b": [1, 2], "c": [1.5, 2.5], "d": [True, False]})
    df_orig = df.copy()
    df2 = df.convert_dtypes()

    if using_copy_on_write:
        if using_infer_string and HAS_PYARROW:
            # TODO the default nullable string dtype still uses python storage
            # this should be changed to pyarrow if installed
            assert not tm.shares_memory(get_array(df2, "a"), get_array(df, "a"))
        else:
            assert tm.shares_memory(get_array(df2, "a"), get_array(df, "a"))
        assert tm.shares_memory(get_array(df2, "d"), get_array(df, "d"))
        assert tm.shares_memory(get_array(df2, "b"), get_array(df, "b"))
        assert tm.shares_memory(get_array(df2, "c"), get_array(df, "c"))
    else:
        assert not np.shares_memory(get_array(df2, "a"), get_array(df, "a"))
        assert not np.shares_memory(get_array(df2, "b"), get_array(df, "b"))
        assert not np.shares_memory(get_array(df2, "c"), get_array(df, "c"))
        assert not np.shares_memory(get_array(df2, "d"), get_array(df, "d"))

    df2.iloc[0, 0] = "x"
    df2.iloc[0, 1] = 10
    tm.assert_frame_equal(df, df_orig)
