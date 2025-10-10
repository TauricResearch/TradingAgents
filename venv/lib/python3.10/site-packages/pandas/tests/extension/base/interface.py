import warnings

import numpy as np
import pytest

from pandas.compat.numpy import np_version_gt2

from pandas.core.dtypes.cast import construct_1d_object_array_from_listlike
from pandas.core.dtypes.common import is_extension_array_dtype
from pandas.core.dtypes.dtypes import ExtensionDtype

import pandas as pd
import pandas._testing as tm


class BaseInterfaceTests:
    """Tests that the basic interface is satisfied."""

    # ------------------------------------------------------------------------
    # Interface
    # ------------------------------------------------------------------------

    def test_len(self, data):
        assert len(data) == 100

    def test_size(self, data):
        assert data.size == 100

    def test_ndim(self, data):
        assert data.ndim == 1

    def test_can_hold_na_valid(self, data):
        # GH-20761
        assert data._can_hold_na is True

    def test_contains(self, data, data_missing):
        # GH-37867
        # Tests for membership checks. Membership checks for nan-likes is tricky and
        # the settled on rule is: `nan_like in arr` is True if nan_like is
        # arr.dtype.na_value and arr.isna().any() is True. Else the check returns False.

        na_value = data.dtype.na_value
        # ensure data without missing values
        data = data[~data.isna()]

        # first elements are non-missing
        assert data[0] in data
        assert data_missing[0] in data_missing

        # check the presence of na_value
        assert na_value in data_missing
        assert na_value not in data

        # the data can never contain other nan-likes than na_value
        for na_value_obj in tm.NULL_OBJECTS:
            if na_value_obj is na_value or type(na_value_obj) == type(na_value):
                # type check for e.g. two instances of Decimal("NAN")
                continue
            assert na_value_obj not in data
            assert na_value_obj not in data_missing

    def test_memory_usage(self, data):
        s = pd.Series(data)
        result = s.memory_usage(index=False)
        assert result == s.nbytes

    def test_array_interface(self, data):
        result = np.array(data)
        assert result[0] == data[0]

        result = np.array(data, dtype=object)
        expected = np.array(list(data), dtype=object)
        if expected.ndim > 1:
            # nested data, explicitly construct as 1D
            expected = construct_1d_object_array_from_listlike(list(data))
        tm.assert_numpy_array_equal(result, expected)

    def test_array_interface_copy(self, data):
        result_copy1 = np.array(data, copy=True)
        result_copy2 = np.array(data, copy=True)
        assert not np.may_share_memory(result_copy1, result_copy2)

        if not np_version_gt2:
            # copy=False semantics are only supported in NumPy>=2.
            return

        warning_raised = False
        msg = "Starting with NumPy 2.0, the behavior of the 'copy' keyword has changed"
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result_nocopy1 = np.array(data, copy=False)
            assert len(w) <= 1
            if len(w):
                warning_raised = True
                assert msg in str(w[0].message)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result_nocopy2 = np.array(data, copy=False)
            assert len(w) <= 1
            if len(w):
                warning_raised = True
                assert msg in str(w[0].message)

        if not warning_raised:
            # If copy=False was given and did not raise, these must share the same data
            assert np.may_share_memory(result_nocopy1, result_nocopy2)

    def test_is_extension_array_dtype(self, data):
        assert is_extension_array_dtype(data)
        assert is_extension_array_dtype(data.dtype)
        assert is_extension_array_dtype(pd.Series(data))
        assert isinstance(data.dtype, ExtensionDtype)

    def test_no_values_attribute(self, data):
        # GH-20735: EA's with .values attribute give problems with internal
        # code, disallowing this for now until solved
        assert not hasattr(data, "values")
        assert not hasattr(data, "_values")

    def test_is_numeric_honored(self, data):
        result = pd.Series(data)
        if hasattr(result._mgr, "blocks"):
            assert result._mgr.blocks[0].is_numeric is data.dtype._is_numeric

    def test_isna_extension_array(self, data_missing):
        # If your `isna` returns an ExtensionArray, you must also implement
        # _reduce. At the *very* least, you must implement any and all
        na = data_missing.isna()
        if is_extension_array_dtype(na):
            assert na._reduce("any")
            assert na.any()

            assert not na._reduce("all")
            assert not na.all()

            assert na.dtype._is_boolean

    def test_copy(self, data):
        # GH#27083 removing deep keyword from EA.copy
        assert data[0] != data[1]
        result = data.copy()

        if data.dtype._is_immutable:
            pytest.skip(f"test_copy assumes mutability and {data.dtype} is immutable")

        data[1] = data[0]
        assert result[1] != result[0]

    def test_view(self, data):
        # view with no dtype should return a shallow copy, *not* the same
        #  object
        assert data[1] != data[0]

        result = data.view()
        assert result is not data
        assert type(result) == type(data)

        if data.dtype._is_immutable:
            pytest.skip(f"test_view assumes mutability and {data.dtype} is immutable")

        result[1] = result[0]
        assert data[1] == data[0]

        # check specifically that the `dtype` kwarg is accepted
        data.view(dtype=None)

    def test_tolist(self, data):
        result = data.tolist()
        expected = list(data)
        assert isinstance(result, list)
        assert result == expected
