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
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from pandas._libs import (
    Period,
    iNaT,
)
from pandas.compat import is_platform_windows
from pandas.compat.numpy import np_version_gte1p24

from pandas.core.dtypes.dtypes import PeriodDtype

import pandas._testing as tm
from pandas.core.arrays import PeriodArray
from pandas.tests.extension import base

if TYPE_CHECKING:
    import pandas as pd


@pytest.fixture(params=["D", "2D"])
def dtype(request):
    return PeriodDtype(freq=request.param)


@pytest.fixture
def data(dtype):
    return PeriodArray(np.arange(1970, 2070), dtype=dtype)


@pytest.fixture
def data_for_sorting(dtype):
    return PeriodArray([2018, 2019, 2017], dtype=dtype)


@pytest.fixture
def data_missing(dtype):
    return PeriodArray([iNaT, 2017], dtype=dtype)


@pytest.fixture
def data_missing_for_sorting(dtype):
    return PeriodArray([2018, iNaT, 2017], dtype=dtype)


@pytest.fixture
def data_for_grouping(dtype):
    B = 2018
    NA = iNaT
    A = 2017
    C = 2019
    return PeriodArray([B, B, NA, NA, A, A, B, C], dtype=dtype)


class TestPeriodArray(base.ExtensionTests):
    def _get_expected_exception(self, op_name, obj, other):
        if op_name in ("__sub__", "__rsub__"):
            return None
        return super()._get_expected_exception(op_name, obj, other)

    def _supports_accumulation(self, ser, op_name: str) -> bool:
        return op_name in ["cummin", "cummax"]

    def _supports_reduction(self, obj, op_name: str) -> bool:
        return op_name in ["min", "max", "median"]

    def check_reduce(self, ser: pd.Series, op_name: str, skipna: bool):
        if op_name == "median":
            res_op = getattr(ser, op_name)

            alt = ser.astype("int64")

            exp_op = getattr(alt, op_name)
            result = res_op(skipna=skipna)
            expected = exp_op(skipna=skipna)
            # error: Item "dtype[Any]" of "dtype[Any] | ExtensionDtype" has no
            # attribute "freq"
            freq = ser.dtype.freq  # type: ignore[union-attr]
            expected = Period._from_ordinal(int(expected), freq=freq)
            tm.assert_almost_equal(result, expected)

        else:
            return super().check_reduce(ser, op_name, skipna)

    @pytest.mark.parametrize("periods", [1, -2])
    def test_diff(self, data, periods):
        if is_platform_windows() and np_version_gte1p24:
            with tm.assert_produces_warning(RuntimeWarning, check_stacklevel=False):
                super().test_diff(data, periods)
        else:
            super().test_diff(data, periods)

    @pytest.mark.parametrize("na_action", [None, "ignore"])
    def test_map(self, data, na_action):
        result = data.map(lambda x: x, na_action=na_action)
        tm.assert_extension_array_equal(result, data)


class Test2DCompat(base.NDArrayBacked2DTests):
    pass
