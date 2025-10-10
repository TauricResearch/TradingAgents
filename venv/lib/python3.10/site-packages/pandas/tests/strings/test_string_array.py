import numpy as np
import pytest

from pandas._libs import lib

from pandas import (
    NA,
    DataFrame,
    Series,
    _testing as tm,
    option_context,
)


def test_string_array(nullable_string_dtype, any_string_method):
    method_name, args, kwargs = any_string_method

    data = ["a", "bb", np.nan, "ccc"]
    a = Series(data, dtype=object)
    b = Series(data, dtype=nullable_string_dtype)

    if method_name == "decode":
        with pytest.raises(TypeError, match="a bytes-like object is required"):
            getattr(b.str, method_name)(*args, **kwargs)
        return

    expected = getattr(a.str, method_name)(*args, **kwargs)
    result = getattr(b.str, method_name)(*args, **kwargs)

    if isinstance(expected, Series):
        if expected.dtype == "object" and lib.is_string_array(
            expected.dropna().values,
        ):
            assert result.dtype == nullable_string_dtype
            result = result.astype(object)

        elif expected.dtype == "object" and lib.is_bool_array(
            expected.values, skipna=True
        ):
            assert result.dtype == "boolean"
            expected = expected.astype("boolean")

        elif expected.dtype == "bool":
            assert result.dtype == "boolean"
            result = result.astype("bool")

        elif expected.dtype == "float" and expected.isna().any():
            assert result.dtype == "Int64"
            result = result.astype("float")

        if expected.dtype == object:
            # GH#18463
            expected[expected.isna()] = NA

    elif isinstance(expected, DataFrame):
        columns = expected.select_dtypes(include="object").columns
        assert all(result[columns].dtypes == nullable_string_dtype)
        result[columns] = result[columns].astype(object)
        with option_context("future.no_silent_downcasting", True):
            expected[columns] = expected[columns].fillna(NA)  # GH#18463

    tm.assert_equal(result, expected)


@pytest.mark.parametrize(
    "method,expected",
    [
        ("count", [2, None]),
        ("find", [0, None]),
        ("index", [0, None]),
        ("rindex", [2, None]),
    ],
)
def test_string_array_numeric_integer_array(nullable_string_dtype, method, expected):
    s = Series(["aba", None], dtype=nullable_string_dtype)
    result = getattr(s.str, method)("a")
    expected = Series(expected, dtype="Int64")
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "method,expected",
    [
        ("isdigit", [False, None, True]),
        ("isalpha", [True, None, False]),
        ("isalnum", [True, None, True]),
        ("isnumeric", [False, None, True]),
    ],
)
def test_string_array_boolean_array(nullable_string_dtype, method, expected):
    s = Series(["a", None, "1"], dtype=nullable_string_dtype)
    result = getattr(s.str, method)()
    expected = Series(expected, dtype="boolean")
    tm.assert_series_equal(result, expected)


def test_string_array_extract(nullable_string_dtype):
    # https://github.com/pandas-dev/pandas/issues/30969
    # Only expand=False & multiple groups was failing

    a = Series(["a1", "b2", "cc"], dtype=nullable_string_dtype)
    b = Series(["a1", "b2", "cc"], dtype="object")
    pat = r"(\w)(\d)"

    result = a.str.extract(pat, expand=False)
    expected = b.str.extract(pat, expand=False)
    expected = expected.fillna(NA)  # GH#18463
    assert all(result.dtypes == nullable_string_dtype)

    result = result.astype(object)
    tm.assert_equal(result, expected)
