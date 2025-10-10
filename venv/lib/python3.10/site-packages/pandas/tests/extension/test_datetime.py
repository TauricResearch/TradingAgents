"""
This file contains a minimal set of tests for compliance with the extension
array interface test suite, and should contain no other tests.
The test suite for the full functionality of the array is located in
`pandas/tests/arrays/`.

The tests in this file are inherited from the BaseExtensionTests, and only
minimal tweaks should be applied to get the tests passing (by overwriting a
parent method).

Additional tests should either be added to one of the BaseExtensionTests
classes (if they are relevant for the extension interface for all dtypes), or
be added to the array-specific tests in `pandas/tests/arrays/`.

"""
import numpy as np
import pytest

from pandas.core.dtypes.dtypes import DatetimeTZDtype

import pandas as pd
import pandas._testing as tm
from pandas.core.arrays import DatetimeArray
from pandas.tests.extension import base


@pytest.fixture(params=["US/Central"])
def dtype(request):
    return DatetimeTZDtype(unit="ns", tz=request.param)


@pytest.fixture
def data(dtype):
    data = DatetimeArray._from_sequence(
        pd.date_range("2000", periods=100, tz=dtype.tz), dtype=dtype
    )
    return data


@pytest.fixture
def data_missing(dtype):
    return DatetimeArray._from_sequence(
        np.array(["NaT", "2000-01-01"], dtype="datetime64[ns]"), dtype=dtype
    )


@pytest.fixture
def data_for_sorting(dtype):
    a = pd.Timestamp("2000-01-01")
    b = pd.Timestamp("2000-01-02")
    c = pd.Timestamp("2000-01-03")
    return DatetimeArray._from_sequence(
        np.array([b, c, a], dtype="datetime64[ns]"), dtype=dtype
    )


@pytest.fixture
def data_missing_for_sorting(dtype):
    a = pd.Timestamp("2000-01-01")
    b = pd.Timestamp("2000-01-02")
    return DatetimeArray._from_sequence(
        np.array([b, "NaT", a], dtype="datetime64[ns]"), dtype=dtype
    )


@pytest.fixture
def data_for_grouping(dtype):
    """
    Expected to be like [B, B, NA, NA, A, A, B, C]

    Where A < B < C and NA is missing
    """
    a = pd.Timestamp("2000-01-01")
    b = pd.Timestamp("2000-01-02")
    c = pd.Timestamp("2000-01-03")
    na = "NaT"
    return DatetimeArray._from_sequence(
        np.array([b, b, na, na, a, a, b, c], dtype="datetime64[ns]"), dtype=dtype
    )


@pytest.fixture
def na_cmp():
    def cmp(a, b):
        return a is pd.NaT and a is b

    return cmp


# ----------------------------------------------------------------------------
class TestDatetimeArray(base.ExtensionTests):
    def _get_expected_exception(self, op_name, obj, other):
        if op_name in ["__sub__", "__rsub__"]:
            return None
        return super()._get_expected_exception(op_name, obj, other)

    def _supports_accumulation(self, ser, op_name: str) -> bool:
        return op_name in ["cummin", "cummax"]

    def _supports_reduction(self, obj, op_name: str) -> bool:
        return op_name in ["min", "max", "median", "mean", "std", "any", "all"]

    @pytest.mark.parametrize("skipna", [True, False])
    def test_reduce_series_boolean(self, data, all_boolean_reductions, skipna):
        meth = all_boolean_reductions
        msg = f"'{meth}' with datetime64 dtypes is deprecated and will raise in"
        with tm.assert_produces_warning(
            FutureWarning, match=msg, check_stacklevel=False
        ):
            super().test_reduce_series_boolean(data, all_boolean_reductions, skipna)

    def test_series_constructor(self, data):
        # Series construction drops any .freq attr
        data = data._with_freq(None)
        super().test_series_constructor(data)

    @pytest.mark.parametrize("na_action", [None, "ignore"])
    def test_map(self, data, na_action):
        result = data.map(lambda x: x, na_action=na_action)
        tm.assert_extension_array_equal(result, data)

    def check_reduce(self, ser: pd.Series, op_name: str, skipna: bool):
        if op_name in ["median", "mean", "std"]:
            alt = ser.astype("int64")

            res_op = getattr(ser, op_name)
            exp_op = getattr(alt, op_name)
            result = res_op(skipna=skipna)
            expected = exp_op(skipna=skipna)
            if op_name in ["mean", "median"]:
                # error: Item "dtype[Any]" of "dtype[Any] | ExtensionDtype"
                # has no attribute "tz"
                tz = ser.dtype.tz  # type: ignore[union-attr]
                expected = pd.Timestamp(expected, tz=tz)
            else:
                expected = pd.Timedelta(expected)
            tm.assert_almost_equal(result, expected)

        else:
            return super().check_reduce(ser, op_name, skipna)


class Test2DCompat(base.NDArrayBacked2DTests):
    pass
