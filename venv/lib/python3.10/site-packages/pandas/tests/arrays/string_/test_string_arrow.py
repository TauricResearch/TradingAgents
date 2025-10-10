import pickle
import re

import numpy as np
import pytest

import pandas.util._test_decorators as td

import pandas as pd
import pandas._testing as tm
from pandas.core.arrays.string_ import (
    StringArray,
    StringDtype,
)
from pandas.core.arrays.string_arrow import (
    ArrowStringArray,
    ArrowStringArrayNumpySemantics,
)


def test_eq_all_na():
    pytest.importorskip("pyarrow")
    a = pd.array([pd.NA, pd.NA], dtype=StringDtype("pyarrow"))
    result = a == a
    expected = pd.array([pd.NA, pd.NA], dtype="boolean[pyarrow]")
    tm.assert_extension_array_equal(result, expected)


def test_config(string_storage, using_infer_string):
    # with the default string_storage setting
    # always "python" at the moment
    assert StringDtype().storage == "python"

    with pd.option_context("string_storage", string_storage):
        assert StringDtype().storage == string_storage
        result = pd.array(["a", "b"])
        assert result.dtype.storage == string_storage

    # pd.array(..) by default always returns the NA-variant
    dtype = StringDtype(string_storage, na_value=pd.NA)
    expected = dtype.construct_array_type()._from_sequence(["a", "b"], dtype=dtype)
    tm.assert_equal(result, expected)


def test_config_bad_storage_raises():
    msg = re.escape("Value must be one of python|pyarrow")
    with pytest.raises(ValueError, match=msg):
        pd.options.mode.string_storage = "foo"


@pytest.mark.parametrize("chunked", [True, False])
@pytest.mark.parametrize("array_lib", ["numpy", "pyarrow"])
def test_constructor_not_string_type_raises(array_lib, chunked):
    pa = pytest.importorskip("pyarrow")

    array_lib = pa if array_lib == "pyarrow" else np

    arr = array_lib.array([1, 2, 3])
    if chunked:
        if array_lib is np:
            pytest.skip("chunked not applicable to numpy array")
        arr = pa.chunked_array(arr)
    if array_lib is np:
        msg = "Unsupported type '<class 'numpy.ndarray'>' for ArrowExtensionArray"
    else:
        msg = re.escape(
            "ArrowStringArray requires a PyArrow (chunked) array of large_string type"
        )
    with pytest.raises(ValueError, match=msg):
        ArrowStringArray(arr)


@pytest.mark.parametrize("chunked", [True, False])
def test_constructor_not_string_type_value_dictionary_raises(chunked):
    pa = pytest.importorskip("pyarrow")

    arr = pa.array([1, 2, 3], pa.dictionary(pa.int32(), pa.int32()))
    if chunked:
        arr = pa.chunked_array(arr)

    msg = re.escape(
        "ArrowStringArray requires a PyArrow (chunked) array of large_string type"
    )
    with pytest.raises(ValueError, match=msg):
        ArrowStringArray(arr)


@pytest.mark.parametrize("string_type", ["string", "large_string"])
@pytest.mark.parametrize("chunked", [True, False])
def test_constructor_valid_string_type_value_dictionary(string_type, chunked):
    pa = pytest.importorskip("pyarrow")

    arr = pa.array(["1", "2", "3"], getattr(pa, string_type)()).dictionary_encode()
    if chunked:
        arr = pa.chunked_array(arr)

    arr = ArrowStringArray(arr)
    # dictionary type get converted to dense large string array
    assert pa.types.is_large_string(arr._pa_array.type)


@pytest.mark.parametrize("chunked", [True, False])
def test_constructor_valid_string_view(chunked):
    # requires pyarrow>=18 for casting string_view to string
    pa = pytest.importorskip("pyarrow", minversion="18")

    arr = pa.array(["1", "2", "3"], pa.string_view())
    if chunked:
        arr = pa.chunked_array(arr)

    arr = ArrowStringArray(arr)
    # dictionary type get converted to dense large string array
    assert pa.types.is_large_string(arr._pa_array.type)


def test_constructor_from_list():
    # GH#27673
    pytest.importorskip("pyarrow")
    result = pd.Series(["E"], dtype=StringDtype(storage="pyarrow"))
    assert isinstance(result.dtype, StringDtype)
    assert result.dtype.storage == "pyarrow"


def test_from_sequence_wrong_dtype_raises(using_infer_string):
    pytest.importorskip("pyarrow")
    with pd.option_context("string_storage", "python"):
        ArrowStringArray._from_sequence(["a", None, "c"], dtype="string")

    with pd.option_context("string_storage", "pyarrow"):
        ArrowStringArray._from_sequence(["a", None, "c"], dtype="string")

    with pytest.raises(AssertionError, match=None):
        ArrowStringArray._from_sequence(["a", None, "c"], dtype="string[python]")

    ArrowStringArray._from_sequence(["a", None, "c"], dtype="string[pyarrow]")

    if not using_infer_string:
        with pytest.raises(AssertionError, match=None):
            with pd.option_context("string_storage", "python"):
                ArrowStringArray._from_sequence(["a", None, "c"], dtype=StringDtype())

    with pd.option_context("string_storage", "pyarrow"):
        ArrowStringArray._from_sequence(["a", None, "c"], dtype=StringDtype())

    if not using_infer_string:
        with pytest.raises(AssertionError, match=None):
            ArrowStringArray._from_sequence(
                ["a", None, "c"], dtype=StringDtype("python")
            )

    ArrowStringArray._from_sequence(["a", None, "c"], dtype=StringDtype("pyarrow"))

    with pd.option_context("string_storage", "python"):
        StringArray._from_sequence(["a", None, "c"], dtype="string")

    with pd.option_context("string_storage", "pyarrow"):
        StringArray._from_sequence(["a", None, "c"], dtype="string")

    StringArray._from_sequence(["a", None, "c"], dtype="string[python]")

    with pytest.raises(AssertionError, match=None):
        StringArray._from_sequence(["a", None, "c"], dtype="string[pyarrow]")

    if not using_infer_string:
        with pd.option_context("string_storage", "python"):
            StringArray._from_sequence(["a", None, "c"], dtype=StringDtype())

    if not using_infer_string:
        with pytest.raises(AssertionError, match=None):
            with pd.option_context("string_storage", "pyarrow"):
                StringArray._from_sequence(["a", None, "c"], dtype=StringDtype())

    StringArray._from_sequence(["a", None, "c"], dtype=StringDtype("python"))

    with pytest.raises(AssertionError, match=None):
        StringArray._from_sequence(["a", None, "c"], dtype=StringDtype("pyarrow"))


@td.skip_if_installed("pyarrow")
def test_pyarrow_not_installed_raises():
    msg = re.escape("pyarrow>=10.0.1 is required for PyArrow backed")

    with pytest.raises(ImportError, match=msg):
        StringDtype(storage="pyarrow")

    with pytest.raises(ImportError, match=msg):
        ArrowStringArray([])

    with pytest.raises(ImportError, match=msg):
        ArrowStringArrayNumpySemantics([])

    with pytest.raises(ImportError, match=msg):
        ArrowStringArray._from_sequence(["a", None, "b"])


@pytest.mark.parametrize("multiple_chunks", [False, True])
@pytest.mark.parametrize(
    "key, value, expected",
    [
        (-1, "XX", ["a", "b", "c", "d", "XX"]),
        (1, "XX", ["a", "XX", "c", "d", "e"]),
        (1, None, ["a", None, "c", "d", "e"]),
        (1, pd.NA, ["a", None, "c", "d", "e"]),
        ([1, 3], "XX", ["a", "XX", "c", "XX", "e"]),
        ([1, 3], ["XX", "YY"], ["a", "XX", "c", "YY", "e"]),
        ([1, 3], ["XX", None], ["a", "XX", "c", None, "e"]),
        ([1, 3], ["XX", pd.NA], ["a", "XX", "c", None, "e"]),
        ([0, -1], ["XX", "YY"], ["XX", "b", "c", "d", "YY"]),
        ([-1, 0], ["XX", "YY"], ["YY", "b", "c", "d", "XX"]),
        (slice(3, None), "XX", ["a", "b", "c", "XX", "XX"]),
        (slice(2, 4), ["XX", "YY"], ["a", "b", "XX", "YY", "e"]),
        (slice(3, 1, -1), ["XX", "YY"], ["a", "b", "YY", "XX", "e"]),
        (slice(None), "XX", ["XX", "XX", "XX", "XX", "XX"]),
        ([False, True, False, True, False], ["XX", "YY"], ["a", "XX", "c", "YY", "e"]),
    ],
)
def test_setitem(multiple_chunks, key, value, expected):
    pa = pytest.importorskip("pyarrow")

    result = pa.array(list("abcde"))
    expected = pa.array(expected)

    if multiple_chunks:
        result = pa.chunked_array([result[:3], result[3:]])
        expected = pa.chunked_array([expected[:3], expected[3:]])

    result = ArrowStringArray(result)
    expected = ArrowStringArray(expected)

    result[key] = value
    tm.assert_equal(result, expected)


def test_setitem_invalid_indexer_raises():
    pa = pytest.importorskip("pyarrow")

    arr = ArrowStringArray(pa.array(list("abcde")))

    with pytest.raises(IndexError, match=None):
        arr[5] = "foo"

    with pytest.raises(IndexError, match=None):
        arr[-6] = "foo"

    with pytest.raises(IndexError, match=None):
        arr[[0, 5]] = "foo"

    with pytest.raises(IndexError, match=None):
        arr[[0, -6]] = "foo"

    with pytest.raises(IndexError, match=None):
        arr[[True, True, False]] = "foo"

    with pytest.raises(ValueError, match=None):
        arr[[0, 1]] = ["foo", "bar", "baz"]


@pytest.mark.parametrize("na_value", [pd.NA, np.nan])
def test_pickle_roundtrip(na_value):
    # GH 42600
    pytest.importorskip("pyarrow")
    dtype = StringDtype("pyarrow", na_value=na_value)
    expected = pd.Series(range(10), dtype=dtype)
    expected_sliced = expected.head(2)
    full_pickled = pickle.dumps(expected)
    sliced_pickled = pickle.dumps(expected_sliced)

    assert len(full_pickled) > len(sliced_pickled)

    result = pickle.loads(full_pickled)
    tm.assert_series_equal(result, expected)

    result_sliced = pickle.loads(sliced_pickled)
    tm.assert_series_equal(result_sliced, expected_sliced)


def test_string_dtype_error_message():
    # GH#55051
    pytest.importorskip("pyarrow")
    msg = "Storage must be 'python' or 'pyarrow'."
    with pytest.raises(ValueError, match=msg):
        StringDtype("bla")
