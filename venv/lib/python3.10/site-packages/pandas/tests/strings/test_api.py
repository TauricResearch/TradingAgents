import numpy as np
import pytest

from pandas import (
    CategoricalDtype,
    DataFrame,
    Index,
    MultiIndex,
    Series,
    _testing as tm,
    option_context,
)
from pandas.core.strings.accessor import StringMethods

# subset of the full set from pandas/conftest.py
_any_allowed_skipna_inferred_dtype = [
    ("string", ["a", np.nan, "c"]),
    ("bytes", [b"a", np.nan, b"c"]),
    ("empty", [np.nan, np.nan, np.nan]),
    ("empty", []),
    ("mixed-integer", ["a", np.nan, 2]),
]
ids, _ = zip(*_any_allowed_skipna_inferred_dtype)  # use inferred type as id


@pytest.fixture(params=_any_allowed_skipna_inferred_dtype, ids=ids)
def any_allowed_skipna_inferred_dtype(request):
    """
    Fixture for all (inferred) dtypes allowed in StringMethods.__init__

    The covered (inferred) types are:
    * 'string'
    * 'empty'
    * 'bytes'
    * 'mixed'
    * 'mixed-integer'

    Returns
    -------
    inferred_dtype : str
        The string for the inferred dtype from _libs.lib.infer_dtype
    values : np.ndarray
        An array of object dtype that will be inferred to have
        `inferred_dtype`

    Examples
    --------
    >>> from pandas._libs import lib
    >>>
    >>> def test_something(any_allowed_skipna_inferred_dtype):
    ...     inferred_dtype, values = any_allowed_skipna_inferred_dtype
    ...     # will pass
    ...     assert lib.infer_dtype(values, skipna=True) == inferred_dtype
    ...
    ...     # constructor for .str-accessor will also pass
    ...     Series(values).str
    """
    inferred_dtype, values = request.param
    values = np.array(values, dtype=object)  # object dtype to avoid casting

    # correctness of inference tested in tests/dtypes/test_inference.py
    return inferred_dtype, values


def test_api(any_string_dtype):
    # GH 6106, GH 9322
    assert Series.str is StringMethods
    assert isinstance(Series([""], dtype=any_string_dtype).str, StringMethods)


def test_api_mi_raises():
    # GH 23679
    mi = MultiIndex.from_arrays([["a", "b", "c"]])
    msg = "Can only use .str accessor with Index, not MultiIndex"
    with pytest.raises(AttributeError, match=msg):
        mi.str
    assert not hasattr(mi, "str")


@pytest.mark.parametrize("dtype", [object, "category"])
def test_api_per_dtype(index_or_series, dtype, any_skipna_inferred_dtype):
    # one instance of parametrized fixture
    box = index_or_series
    inferred_dtype, values = any_skipna_inferred_dtype

    t = box(values, dtype=dtype)  # explicit dtype to avoid casting

    types_passing_constructor = [
        "string",
        "unicode",
        "empty",
        "bytes",
        "mixed",
        "mixed-integer",
    ]
    if inferred_dtype in types_passing_constructor:
        # GH 6106
        assert isinstance(t.str, StringMethods)
    else:
        # GH 9184, GH 23011, GH 23163
        msg = "Can only use .str accessor with string values.*"
        with pytest.raises(AttributeError, match=msg):
            t.str
        assert not hasattr(t, "str")


@pytest.mark.parametrize("dtype", [object, "category"])
def test_api_per_method(
    index_or_series,
    dtype,
    any_allowed_skipna_inferred_dtype,
    any_string_method,
    request,
    using_infer_string,
):
    # this test does not check correctness of the different methods,
    # just that the methods work on the specified (inferred) dtypes,
    # and raise on all others
    box = index_or_series

    # one instance of each parametrized fixture
    inferred_dtype, values = any_allowed_skipna_inferred_dtype
    method_name, args, kwargs = any_string_method

    reason = None
    if box is Index and values.size == 0:
        if method_name in ["partition", "rpartition"] and kwargs.get("expand", True):
            raises = TypeError
            reason = "Method cannot deal with empty Index"
        elif method_name == "split" and kwargs.get("expand", None):
            raises = TypeError
            reason = "Split fails on empty Series when expand=True"
        elif method_name == "get_dummies":
            raises = ValueError
            reason = "Need to fortify get_dummies corner cases"

    elif (
        box is Index
        and inferred_dtype == "empty"
        and dtype == object
        and method_name == "get_dummies"
    ):
        raises = ValueError
        reason = "Need to fortify get_dummies corner cases"

    if reason is not None:
        mark = pytest.mark.xfail(raises=raises, reason=reason)
        request.applymarker(mark)

    t = box(values, dtype=dtype)  # explicit dtype to avoid casting
    method = getattr(t.str, method_name)

    if using_infer_string and dtype == "category":
        string_allowed = method_name not in ["decode"]
    else:
        string_allowed = True
    bytes_allowed = method_name in ["decode", "get", "len", "slice"]
    # as of v0.23.4, all methods except 'cat' are very lenient with the
    # allowed data types, just returning NaN for entries that error.
    # This could be changed with an 'errors'-kwarg to the `str`-accessor,
    # see discussion in GH 13877
    mixed_allowed = method_name not in ["cat"]

    allowed_types = (
        ["empty"]
        + ["string", "unicode"] * string_allowed
        + ["bytes"] * bytes_allowed
        + ["mixed", "mixed-integer"] * mixed_allowed
    )

    if inferred_dtype in allowed_types:
        # xref GH 23555, GH 23556
        with option_context("future.no_silent_downcasting", True):
            method(*args, **kwargs)  # works!
    else:
        # GH 23011, GH 23163
        msg = (
            f"Cannot use .str.{method_name} with values of "
            f"inferred dtype {repr(inferred_dtype)}."
            "|a bytes-like object is required, not 'str'"
        )
        with pytest.raises(TypeError, match=msg):
            method(*args, **kwargs)


def test_api_for_categorical(any_string_method, any_string_dtype):
    # https://github.com/pandas-dev/pandas/issues/10661
    s = Series(list("aabb"), dtype=any_string_dtype)
    s = s + " " + s
    c = s.astype("category")
    c = c.astype(CategoricalDtype(c.dtype.categories.astype("object")))
    assert isinstance(c.str, StringMethods)

    method_name, args, kwargs = any_string_method

    result = getattr(c.str, method_name)(*args, **kwargs)
    expected = getattr(s.astype("object").str, method_name)(*args, **kwargs)

    if isinstance(result, DataFrame):
        tm.assert_frame_equal(result, expected)
    elif isinstance(result, Series):
        tm.assert_series_equal(result, expected)
    else:
        # str.cat(others=None) returns string, for example
        assert result == expected
