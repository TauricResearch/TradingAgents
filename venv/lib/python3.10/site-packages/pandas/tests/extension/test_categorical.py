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
import string

import numpy as np
import pytest

from pandas._config import using_string_dtype

import pandas as pd
from pandas import Categorical
import pandas._testing as tm
from pandas.api.types import CategoricalDtype
from pandas.tests.extension import base


def make_data():
    while True:
        values = np.random.default_rng(2).choice(list(string.ascii_letters), size=100)
        # ensure we meet the requirements
        # 1. first two not null
        # 2. first and second are different
        if values[0] != values[1]:
            break
    return values


@pytest.fixture
def dtype():
    return CategoricalDtype()


@pytest.fixture
def data():
    """Length-100 array for this type.

    * data[0] and data[1] should both be non missing
    * data[0] and data[1] should not be equal
    """
    return Categorical(make_data())


@pytest.fixture
def data_missing():
    """Length 2 array with [NA, Valid]"""
    return Categorical([np.nan, "A"])


@pytest.fixture
def data_for_sorting():
    return Categorical(["A", "B", "C"], categories=["C", "A", "B"], ordered=True)


@pytest.fixture
def data_missing_for_sorting():
    return Categorical(["A", None, "B"], categories=["B", "A"], ordered=True)


@pytest.fixture
def data_for_grouping():
    return Categorical(["a", "a", None, None, "b", "b", "a", "c"])


class TestCategorical(base.ExtensionTests):
    @pytest.mark.xfail(reason="Memory usage doesn't match")
    def test_memory_usage(self, data):
        # TODO: Is this deliberate?
        super().test_memory_usage(data)

    def test_contains(self, data, data_missing):
        # GH-37867
        # na value handling in Categorical.__contains__ is deprecated.
        # See base.BaseInterFaceTests.test_contains for more details.

        na_value = data.dtype.na_value
        # ensure data without missing values
        data = data[~data.isna()]

        # first elements are non-missing
        assert data[0] in data
        assert data_missing[0] in data_missing

        # check the presence of na_value
        assert na_value in data_missing
        assert na_value not in data

        # Categoricals can contain other nan-likes than na_value
        for na_value_obj in tm.NULL_OBJECTS:
            if na_value_obj is na_value:
                continue
            assert na_value_obj not in data
            # this section suffers from super method
            if not using_string_dtype():
                assert na_value_obj in data_missing

    def test_empty(self, dtype):
        cls = dtype.construct_array_type()
        result = cls._empty((4,), dtype=dtype)

        assert isinstance(result, cls)
        # the dtype we passed is not initialized, so will not match the
        #  dtype on our result.
        assert result.dtype == CategoricalDtype([])

    @pytest.mark.skip(reason="Backwards compatibility")
    def test_getitem_scalar(self, data):
        # CategoricalDtype.type isn't "correct" since it should
        # be a parent of the elements (object). But don't want
        # to break things by changing.
        super().test_getitem_scalar(data)

    @pytest.mark.xfail(reason="Unobserved categories included")
    def test_value_counts(self, all_data, dropna):
        return super().test_value_counts(all_data, dropna)

    def test_combine_add(self, data_repeated):
        # GH 20825
        # When adding categoricals in combine, result is a string
        orig_data1, orig_data2 = data_repeated(2)
        s1 = pd.Series(orig_data1)
        s2 = pd.Series(orig_data2)
        result = s1.combine(s2, lambda x1, x2: x1 + x2)
        expected = pd.Series(
            [a + b for (a, b) in zip(list(orig_data1), list(orig_data2))]
        )
        tm.assert_series_equal(result, expected)

        val = s1.iloc[0]
        result = s1.combine(val, lambda x1, x2: x1 + x2)
        expected = pd.Series([a + val for a in list(orig_data1)])
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("na_action", [None, "ignore"])
    def test_map(self, data, na_action):
        result = data.map(lambda x: x, na_action=na_action)
        tm.assert_extension_array_equal(result, data)

    def test_arith_frame_with_scalar(self, data, all_arithmetic_operators, request):
        # frame & scalar
        op_name = all_arithmetic_operators
        if op_name == "__rmod__":
            request.applymarker(
                pytest.mark.xfail(
                    reason="rmod never called when string is first argument"
                )
            )
        super().test_arith_frame_with_scalar(data, op_name)

    def test_arith_series_with_scalar(self, data, all_arithmetic_operators, request):
        op_name = all_arithmetic_operators
        if op_name == "__rmod__":
            request.applymarker(
                pytest.mark.xfail(
                    reason="rmod never called when string is first argument"
                )
            )
        super().test_arith_series_with_scalar(data, op_name)

    def _compare_other(self, ser: pd.Series, data, op, other):
        op_name = f"__{op.__name__}__"
        if op_name not in ["__eq__", "__ne__"]:
            msg = "Unordered Categoricals can only compare equality or not"
            with pytest.raises(TypeError, match=msg):
                op(data, other)
        else:
            return super()._compare_other(ser, data, op, other)

    @pytest.mark.xfail(reason="Categorical overrides __repr__")
    @pytest.mark.parametrize("size", ["big", "small"])
    def test_array_repr(self, data, size):
        super().test_array_repr(data, size)

    @pytest.mark.xfail(reason="TBD")
    @pytest.mark.parametrize("as_index", [True, False])
    def test_groupby_extension_agg(self, as_index, data_for_grouping):
        super().test_groupby_extension_agg(as_index, data_for_grouping)


class Test2DCompat(base.NDArrayBacked2DTests):
    def test_repr_2d(self, data):
        # Categorical __repr__ doesn't include "Categorical", so we need
        #  to special-case
        res = repr(data.reshape(1, -1))
        assert res.count("\nCategories") == 1

        res = repr(data.reshape(-1, 1))
        assert res.count("\nCategories") == 1
