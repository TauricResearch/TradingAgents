import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm
from pandas.api.types import (
    infer_dtype,
    is_object_dtype,
    is_string_dtype,
)


class BaseDtypeTests:
    """Base class for ExtensionDtype classes"""

    def test_name(self, dtype):
        assert isinstance(dtype.name, str)

    def test_kind(self, dtype):
        valid = set("biufcmMOSUV")
        assert dtype.kind in valid

    def test_is_dtype_from_name(self, dtype):
        result = type(dtype).is_dtype(dtype.name)
        assert result is True

    def test_is_dtype_unboxes_dtype(self, data, dtype):
        assert dtype.is_dtype(data) is True

    def test_is_dtype_from_self(self, dtype):
        result = type(dtype).is_dtype(dtype)
        assert result is True

    def test_is_dtype_other_input(self, dtype):
        assert dtype.is_dtype([1, 2, 3]) is False

    def test_is_not_string_type(self, dtype):
        assert not is_string_dtype(dtype)

    def test_is_not_object_type(self, dtype):
        assert not is_object_dtype(dtype)

    def test_eq_with_str(self, dtype):
        assert dtype == dtype.name
        assert dtype != dtype.name + "-suffix"

    def test_eq_with_numpy_object(self, dtype):
        assert dtype != np.dtype("object")

    def test_eq_with_self(self, dtype):
        assert dtype == dtype
        assert dtype != object()

    def test_array_type(self, data, dtype):
        assert dtype.construct_array_type() is type(data)

    def test_check_dtype(self, data):
        dtype = data.dtype

        # check equivalency for using .dtypes
        df = pd.DataFrame(
            {
                "A": pd.Series(data, dtype=dtype),
                "B": data,
                "C": pd.Series(["foo"] * len(data), dtype=object),
                "D": 1,
            }
        )
        result = df.dtypes == str(dtype)
        assert np.dtype("int64") != "Int64"

        expected = pd.Series([True, True, False, False], index=list("ABCD"))

        tm.assert_series_equal(result, expected)

        expected = pd.Series([True, True, False, False], index=list("ABCD"))
        result = df.dtypes.apply(str) == str(dtype)
        tm.assert_series_equal(result, expected)

    def test_hashable(self, dtype):
        hash(dtype)  # no error

    def test_str(self, dtype):
        assert str(dtype) == dtype.name

    def test_eq(self, dtype):
        assert dtype == dtype.name
        assert dtype != "anonther_type"

    def test_construct_from_string_own_name(self, dtype):
        result = dtype.construct_from_string(dtype.name)
        assert type(result) is type(dtype)

        # check OK as classmethod
        result = type(dtype).construct_from_string(dtype.name)
        assert type(result) is type(dtype)

    def test_construct_from_string_another_type_raises(self, dtype):
        msg = f"Cannot construct a '{type(dtype).__name__}' from 'another_type'"
        with pytest.raises(TypeError, match=msg):
            type(dtype).construct_from_string("another_type")

    def test_construct_from_string_wrong_type_raises(self, dtype):
        with pytest.raises(
            TypeError,
            match="'construct_from_string' expects a string, got <class 'int'>",
        ):
            type(dtype).construct_from_string(0)

    def test_get_common_dtype(self, dtype):
        # in practice we will not typically call this with a 1-length list
        # (we shortcut to just use that dtype as the common dtype), but
        # still testing as good practice to have this working (and it is the
        # only case we can test in general)
        assert dtype._get_common_dtype([dtype]) == dtype

    @pytest.mark.parametrize("skipna", [True, False])
    def test_infer_dtype(self, data, data_missing, skipna):
        # only testing that this works without raising an error
        res = infer_dtype(data, skipna=skipna)
        assert isinstance(res, str)
        res = infer_dtype(data_missing, skipna=skipna)
        assert isinstance(res, str)
