"""
These the test the public routines exposed in types/common.py
related to inference and not otherwise tested in types/test_common.py

"""
import collections
from collections import namedtuple
from collections.abc import Iterator
from datetime import (
    date,
    datetime,
    time,
    timedelta,
)
from decimal import Decimal
from fractions import Fraction
from io import StringIO
import itertools
from numbers import Number
import re
import sys
from typing import (
    Generic,
    TypeVar,
)

import numpy as np
import pytest
import pytz

from pandas._libs import (
    lib,
    missing as libmissing,
    ops as libops,
)
from pandas.compat.numpy import np_version_gt2

from pandas.core.dtypes import inference
from pandas.core.dtypes.cast import find_result_type
from pandas.core.dtypes.common import (
    ensure_int32,
    is_bool,
    is_complex,
    is_datetime64_any_dtype,
    is_datetime64_dtype,
    is_datetime64_ns_dtype,
    is_datetime64tz_dtype,
    is_float,
    is_integer,
    is_number,
    is_scalar,
    is_scipy_sparse,
    is_timedelta64_dtype,
    is_timedelta64_ns_dtype,
)

import pandas as pd
from pandas import (
    Categorical,
    DataFrame,
    DateOffset,
    DatetimeIndex,
    Index,
    Interval,
    Period,
    PeriodIndex,
    Series,
    Timedelta,
    TimedeltaIndex,
    Timestamp,
)
import pandas._testing as tm
from pandas.core.arrays import (
    BooleanArray,
    FloatingArray,
    IntegerArray,
)


@pytest.fixture(params=[True, False], ids=str)
def coerce(request):
    return request.param


class MockNumpyLikeArray:
    """
    A class which is numpy-like (e.g. Pint's Quantity) but not actually numpy

    The key is that it is not actually a numpy array so
    ``util.is_array(mock_numpy_like_array_instance)`` returns ``False``. Other
    important properties are that the class defines a :meth:`__iter__` method
    (so that ``isinstance(abc.Iterable)`` returns ``True``) and has a
    :meth:`ndim` property, as pandas special-cases 0-dimensional arrays in some
    cases.

    We expect pandas to behave with respect to such duck arrays exactly as
    with real numpy arrays. In particular, a 0-dimensional duck array is *NOT*
    a scalar (`is_scalar(np.array(1)) == False`), but it is not list-like either.
    """

    def __init__(self, values) -> None:
        self._values = values

    def __iter__(self) -> Iterator:
        iter_values = iter(self._values)

        def it_outer():
            yield from iter_values

        return it_outer()

    def __len__(self) -> int:
        return len(self._values)

    def __array__(self, dtype=None, copy=None):
        return np.asarray(self._values, dtype=dtype)

    @property
    def ndim(self):
        return self._values.ndim

    @property
    def dtype(self):
        return self._values.dtype

    @property
    def size(self):
        return self._values.size

    @property
    def shape(self):
        return self._values.shape


# collect all objects to be tested for list-like-ness; use tuples of objects,
# whether they are list-like or not (special casing for sets), and their ID
ll_params = [
    ([1], True, "list"),
    ([], True, "list-empty"),
    ((1,), True, "tuple"),
    ((), True, "tuple-empty"),
    ({"a": 1}, True, "dict"),
    ({}, True, "dict-empty"),
    ({"a", 1}, "set", "set"),
    (set(), "set", "set-empty"),
    (frozenset({"a", 1}), "set", "frozenset"),
    (frozenset(), "set", "frozenset-empty"),
    (iter([1, 2]), True, "iterator"),
    (iter([]), True, "iterator-empty"),
    ((x for x in [1, 2]), True, "generator"),
    ((_ for _ in []), True, "generator-empty"),
    (Series([1]), True, "Series"),
    (Series([], dtype=object), True, "Series-empty"),
    # Series.str will still raise a TypeError if iterated
    (Series(["a"]).str, True, "StringMethods"),
    (Series([], dtype="O").str, True, "StringMethods-empty"),
    (Index([1]), True, "Index"),
    (Index([]), True, "Index-empty"),
    (DataFrame([[1]]), True, "DataFrame"),
    (DataFrame(), True, "DataFrame-empty"),
    (np.ndarray((2,) * 1), True, "ndarray-1d"),
    (np.array([]), True, "ndarray-1d-empty"),
    (np.ndarray((2,) * 2), True, "ndarray-2d"),
    (np.array([[]]), True, "ndarray-2d-empty"),
    (np.ndarray((2,) * 3), True, "ndarray-3d"),
    (np.array([[[]]]), True, "ndarray-3d-empty"),
    (np.ndarray((2,) * 4), True, "ndarray-4d"),
    (np.array([[[[]]]]), True, "ndarray-4d-empty"),
    (np.array(2), False, "ndarray-0d"),
    (MockNumpyLikeArray(np.ndarray((2,) * 1)), True, "duck-ndarray-1d"),
    (MockNumpyLikeArray(np.array([])), True, "duck-ndarray-1d-empty"),
    (MockNumpyLikeArray(np.ndarray((2,) * 2)), True, "duck-ndarray-2d"),
    (MockNumpyLikeArray(np.array([[]])), True, "duck-ndarray-2d-empty"),
    (MockNumpyLikeArray(np.ndarray((2,) * 3)), True, "duck-ndarray-3d"),
    (MockNumpyLikeArray(np.array([[[]]])), True, "duck-ndarray-3d-empty"),
    (MockNumpyLikeArray(np.ndarray((2,) * 4)), True, "duck-ndarray-4d"),
    (MockNumpyLikeArray(np.array([[[[]]]])), True, "duck-ndarray-4d-empty"),
    (MockNumpyLikeArray(np.array(2)), False, "duck-ndarray-0d"),
    (1, False, "int"),
    (b"123", False, "bytes"),
    (b"", False, "bytes-empty"),
    ("123", False, "string"),
    ("", False, "string-empty"),
    (str, False, "string-type"),
    (object(), False, "object"),
    (np.nan, False, "NaN"),
    (None, False, "None"),
]
objs, expected, ids = zip(*ll_params)


@pytest.fixture(params=zip(objs, expected), ids=ids)
def maybe_list_like(request):
    return request.param


def test_is_list_like(maybe_list_like):
    obj, expected = maybe_list_like
    expected = True if expected == "set" else expected
    assert inference.is_list_like(obj) == expected


def test_is_list_like_disallow_sets(maybe_list_like):
    obj, expected = maybe_list_like
    expected = False if expected == "set" else expected
    assert inference.is_list_like(obj, allow_sets=False) == expected


def test_is_list_like_recursion():
    # GH 33721
    # interpreter would crash with SIGABRT
    def list_like():
        inference.is_list_like([])
        list_like()

    rec_limit = sys.getrecursionlimit()
    try:
        # Limit to avoid stack overflow on Windows CI
        sys.setrecursionlimit(100)
        with tm.external_error_raised(RecursionError):
            list_like()
    finally:
        sys.setrecursionlimit(rec_limit)


def test_is_list_like_iter_is_none():
    # GH 43373
    # is_list_like was yielding false positives with __iter__ == None
    class NotListLike:
        def __getitem__(self, item):
            return self

        __iter__ = None

    assert not inference.is_list_like(NotListLike())


def test_is_list_like_generic():
    # GH 49649
    # is_list_like was yielding false positives for Generic classes in python 3.11
    T = TypeVar("T")

    class MyDataFrame(DataFrame, Generic[T]):
        ...

    tstc = MyDataFrame[int]
    tst = MyDataFrame[int]({"x": [1, 2, 3]})

    assert not inference.is_list_like(tstc)
    assert isinstance(tst, DataFrame)
    assert inference.is_list_like(tst)


def test_is_sequence():
    is_seq = inference.is_sequence
    assert is_seq((1, 2))
    assert is_seq([1, 2])
    assert not is_seq("abcd")
    assert not is_seq(np.int64)

    class A:
        def __getitem__(self, item):
            return 1

    assert not is_seq(A())


def test_is_array_like():
    assert inference.is_array_like(Series([], dtype=object))
    assert inference.is_array_like(Series([1, 2]))
    assert inference.is_array_like(np.array(["a", "b"]))
    assert inference.is_array_like(Index(["2016-01-01"]))
    assert inference.is_array_like(np.array([2, 3]))
    assert inference.is_array_like(MockNumpyLikeArray(np.array([2, 3])))

    class DtypeList(list):
        dtype = "special"

    assert inference.is_array_like(DtypeList())

    assert not inference.is_array_like([1, 2, 3])
    assert not inference.is_array_like(())
    assert not inference.is_array_like("foo")
    assert not inference.is_array_like(123)


@pytest.mark.parametrize(
    "inner",
    [
        [],
        [1],
        (1,),
        (1, 2),
        {"a": 1},
        {1, "a"},
        Series([1]),
        Series([], dtype=object),
        Series(["a"]).str,
        (x for x in range(5)),
    ],
)
@pytest.mark.parametrize("outer", [list, Series, np.array, tuple])
def test_is_nested_list_like_passes(inner, outer):
    result = outer([inner for _ in range(5)])
    assert inference.is_list_like(result)


@pytest.mark.parametrize(
    "obj",
    [
        "abc",
        [],
        [1],
        (1,),
        ["a"],
        "a",
        {"a"},
        [1, 2, 3],
        Series([1]),
        DataFrame({"A": [1]}),
        ([1, 2] for _ in range(5)),
    ],
)
def test_is_nested_list_like_fails(obj):
    assert not inference.is_nested_list_like(obj)


@pytest.mark.parametrize("ll", [{}, {"A": 1}, Series([1]), collections.defaultdict()])
def test_is_dict_like_passes(ll):
    assert inference.is_dict_like(ll)


@pytest.mark.parametrize(
    "ll",
    [
        "1",
        1,
        [1, 2],
        (1, 2),
        range(2),
        Index([1]),
        dict,
        collections.defaultdict,
        Series,
    ],
)
def test_is_dict_like_fails(ll):
    assert not inference.is_dict_like(ll)


@pytest.mark.parametrize("has_keys", [True, False])
@pytest.mark.parametrize("has_getitem", [True, False])
@pytest.mark.parametrize("has_contains", [True, False])
def test_is_dict_like_duck_type(has_keys, has_getitem, has_contains):
    class DictLike:
        def __init__(self, d) -> None:
            self.d = d

        if has_keys:

            def keys(self):
                return self.d.keys()

        if has_getitem:

            def __getitem__(self, key):
                return self.d.__getitem__(key)

        if has_contains:

            def __contains__(self, key) -> bool:
                return self.d.__contains__(key)

    d = DictLike({1: 2})
    result = inference.is_dict_like(d)
    expected = has_keys and has_getitem and has_contains

    assert result is expected


def test_is_file_like():
    class MockFile:
        pass

    is_file = inference.is_file_like

    data = StringIO("data")
    assert is_file(data)

    # No read / write attributes
    # No iterator attributes
    m = MockFile()
    assert not is_file(m)

    MockFile.write = lambda self: 0

    # Write attribute but not an iterator
    m = MockFile()
    assert not is_file(m)

    # gh-16530: Valid iterator just means we have the
    # __iter__ attribute for our purposes.
    MockFile.__iter__ = lambda self: self

    # Valid write-only file
    m = MockFile()
    assert is_file(m)

    del MockFile.write
    MockFile.read = lambda self: 0

    # Valid read-only file
    m = MockFile()
    assert is_file(m)

    # Iterator but no read / write attributes
    data = [1, 2, 3]
    assert not is_file(data)


test_tuple = collections.namedtuple("test_tuple", ["a", "b", "c"])


@pytest.mark.parametrize("ll", [test_tuple(1, 2, 3)])
def test_is_names_tuple_passes(ll):
    assert inference.is_named_tuple(ll)


@pytest.mark.parametrize("ll", [(1, 2, 3), "a", Series({"pi": 3.14})])
def test_is_names_tuple_fails(ll):
    assert not inference.is_named_tuple(ll)


def test_is_hashable():
    # all new-style classes are hashable by default
    class HashableClass:
        pass

    class UnhashableClass1:
        __hash__ = None

    class UnhashableClass2:
        def __hash__(self):
            raise TypeError("Not hashable")

    hashable = (1, 3.14, np.float64(3.14), "a", (), (1,), HashableClass())
    not_hashable = ([], UnhashableClass1())
    abc_hashable_not_really_hashable = (([],), UnhashableClass2())

    for i in hashable:
        assert inference.is_hashable(i)
    for i in not_hashable:
        assert not inference.is_hashable(i)
    for i in abc_hashable_not_really_hashable:
        assert not inference.is_hashable(i)

    # numpy.array is no longer collections.abc.Hashable as of
    # https://github.com/numpy/numpy/pull/5326, just test
    # is_hashable()
    assert not inference.is_hashable(np.array([]))


@pytest.mark.parametrize("ll", [re.compile("ad")])
def test_is_re_passes(ll):
    assert inference.is_re(ll)


@pytest.mark.parametrize("ll", ["x", 2, 3, object()])
def test_is_re_fails(ll):
    assert not inference.is_re(ll)


@pytest.mark.parametrize(
    "ll", [r"a", "x", r"asdf", re.compile("adsf"), r"\u2233\s*", re.compile(r"")]
)
def test_is_recompilable_passes(ll):
    assert inference.is_re_compilable(ll)


@pytest.mark.parametrize("ll", [1, [], object()])
def test_is_recompilable_fails(ll):
    assert not inference.is_re_compilable(ll)


class TestInference:
    @pytest.mark.parametrize(
        "arr",
        [
            np.array(list("abc"), dtype="S1"),
            np.array(list("abc"), dtype="S1").astype(object),
            [b"a", np.nan, b"c"],
        ],
    )
    def test_infer_dtype_bytes(self, arr):
        result = lib.infer_dtype(arr, skipna=True)
        assert result == "bytes"

    @pytest.mark.parametrize(
        "value, expected",
        [
            (float("inf"), True),
            (np.inf, True),
            (-np.inf, False),
            (1, False),
            ("a", False),
        ],
    )
    def test_isposinf_scalar(self, value, expected):
        # GH 11352
        result = libmissing.isposinf_scalar(value)
        assert result is expected

    @pytest.mark.parametrize(
        "value, expected",
        [
            (float("-inf"), True),
            (-np.inf, True),
            (np.inf, False),
            (1, False),
            ("a", False),
        ],
    )
    def test_isneginf_scalar(self, value, expected):
        result = libmissing.isneginf_scalar(value)
        assert result is expected

    @pytest.mark.parametrize(
        "convert_to_masked_nullable, exp",
        [
            (
                True,
                BooleanArray(
                    np.array([True, False], dtype="bool"), np.array([False, True])
                ),
            ),
            (False, np.array([True, np.nan], dtype="object")),
        ],
    )
    def test_maybe_convert_nullable_boolean(self, convert_to_masked_nullable, exp):
        # GH 40687
        arr = np.array([True, np.nan], dtype=object)
        result = libops.maybe_convert_bool(
            arr, set(), convert_to_masked_nullable=convert_to_masked_nullable
        )
        if convert_to_masked_nullable:
            tm.assert_extension_array_equal(BooleanArray(*result), exp)
        else:
            result = result[0]
            tm.assert_numpy_array_equal(result, exp)

    @pytest.mark.parametrize("convert_to_masked_nullable", [True, False])
    @pytest.mark.parametrize("coerce_numeric", [True, False])
    @pytest.mark.parametrize(
        "infinity", ["inf", "inF", "iNf", "Inf", "iNF", "InF", "INf", "INF"]
    )
    @pytest.mark.parametrize("prefix", ["", "-", "+"])
    def test_maybe_convert_numeric_infinities(
        self, coerce_numeric, infinity, prefix, convert_to_masked_nullable
    ):
        # see gh-13274
        result, _ = lib.maybe_convert_numeric(
            np.array([prefix + infinity], dtype=object),
            na_values={"", "NULL", "nan"},
            coerce_numeric=coerce_numeric,
            convert_to_masked_nullable=convert_to_masked_nullable,
        )
        expected = np.array([np.inf if prefix in ["", "+"] else -np.inf])
        tm.assert_numpy_array_equal(result, expected)

    @pytest.mark.parametrize("convert_to_masked_nullable", [True, False])
    def test_maybe_convert_numeric_infinities_raises(self, convert_to_masked_nullable):
        msg = "Unable to parse string"
        with pytest.raises(ValueError, match=msg):
            lib.maybe_convert_numeric(
                np.array(["foo_inf"], dtype=object),
                na_values={"", "NULL", "nan"},
                coerce_numeric=False,
                convert_to_masked_nullable=convert_to_masked_nullable,
            )

    @pytest.mark.parametrize("convert_to_masked_nullable", [True, False])
    def test_maybe_convert_numeric_post_floatify_nan(
        self, coerce, convert_to_masked_nullable
    ):
        # see gh-13314
        data = np.array(["1.200", "-999.000", "4.500"], dtype=object)
        expected = np.array([1.2, np.nan, 4.5], dtype=np.float64)
        nan_values = {-999, -999.0}

        out = lib.maybe_convert_numeric(
            data,
            nan_values,
            coerce,
            convert_to_masked_nullable=convert_to_masked_nullable,
        )
        if convert_to_masked_nullable:
            expected = FloatingArray(expected, np.isnan(expected))
            tm.assert_extension_array_equal(expected, FloatingArray(*out))
        else:
            out = out[0]
            tm.assert_numpy_array_equal(out, expected)

    def test_convert_infs(self):
        arr = np.array(["inf", "inf", "inf"], dtype="O")
        result, _ = lib.maybe_convert_numeric(arr, set(), False)
        assert result.dtype == np.float64

        arr = np.array(["-inf", "-inf", "-inf"], dtype="O")
        result, _ = lib.maybe_convert_numeric(arr, set(), False)
        assert result.dtype == np.float64

    def test_scientific_no_exponent(self):
        # See PR 12215
        arr = np.array(["42E", "2E", "99e", "6e"], dtype="O")
        result, _ = lib.maybe_convert_numeric(arr, set(), False, True)
        assert np.all(np.isnan(result))

    def test_convert_non_hashable(self):
        # GH13324
        # make sure that we are handing non-hashables
        arr = np.array([[10.0, 2], 1.0, "apple"], dtype=object)
        result, _ = lib.maybe_convert_numeric(arr, set(), False, True)
        tm.assert_numpy_array_equal(result, np.array([np.nan, 1.0, np.nan]))

    def test_convert_numeric_uint64(self):
        arr = np.array([2**63], dtype=object)
        exp = np.array([2**63], dtype=np.uint64)
        tm.assert_numpy_array_equal(lib.maybe_convert_numeric(arr, set())[0], exp)

        arr = np.array([str(2**63)], dtype=object)
        exp = np.array([2**63], dtype=np.uint64)
        tm.assert_numpy_array_equal(lib.maybe_convert_numeric(arr, set())[0], exp)

        arr = np.array([np.uint64(2**63)], dtype=object)
        exp = np.array([2**63], dtype=np.uint64)
        tm.assert_numpy_array_equal(lib.maybe_convert_numeric(arr, set())[0], exp)

    @pytest.mark.parametrize(
        "arr",
        [
            np.array([2**63, np.nan], dtype=object),
            np.array([str(2**63), np.nan], dtype=object),
            np.array([np.nan, 2**63], dtype=object),
            np.array([np.nan, str(2**63)], dtype=object),
        ],
    )
    def test_convert_numeric_uint64_nan(self, coerce, arr):
        expected = arr.astype(float) if coerce else arr.copy()
        result, _ = lib.maybe_convert_numeric(arr, set(), coerce_numeric=coerce)
        tm.assert_almost_equal(result, expected)

    @pytest.mark.parametrize("convert_to_masked_nullable", [True, False])
    def test_convert_numeric_uint64_nan_values(
        self, coerce, convert_to_masked_nullable
    ):
        arr = np.array([2**63, 2**63 + 1], dtype=object)
        na_values = {2**63}

        expected = (
            np.array([np.nan, 2**63 + 1], dtype=float) if coerce else arr.copy()
        )
        result = lib.maybe_convert_numeric(
            arr,
            na_values,
            coerce_numeric=coerce,
            convert_to_masked_nullable=convert_to_masked_nullable,
        )
        if convert_to_masked_nullable and coerce:
            expected = IntegerArray(
                np.array([0, 2**63 + 1], dtype="u8"),
                np.array([True, False], dtype="bool"),
            )
            result = IntegerArray(*result)
        else:
            result = result[0]  # discard mask
        tm.assert_almost_equal(result, expected)

    @pytest.mark.parametrize(
        "case",
        [
            np.array([2**63, -1], dtype=object),
            np.array([str(2**63), -1], dtype=object),
            np.array([str(2**63), str(-1)], dtype=object),
            np.array([-1, 2**63], dtype=object),
            np.array([-1, str(2**63)], dtype=object),
            np.array([str(-1), str(2**63)], dtype=object),
        ],
    )
    @pytest.mark.parametrize("convert_to_masked_nullable", [True, False])
    def test_convert_numeric_int64_uint64(
        self, case, coerce, convert_to_masked_nullable
    ):
        expected = case.astype(float) if coerce else case.copy()
        result, _ = lib.maybe_convert_numeric(
            case,
            set(),
            coerce_numeric=coerce,
            convert_to_masked_nullable=convert_to_masked_nullable,
        )

        tm.assert_almost_equal(result, expected)

    @pytest.mark.parametrize("convert_to_masked_nullable", [True, False])
    def test_convert_numeric_string_uint64(self, convert_to_masked_nullable):
        # GH32394
        result = lib.maybe_convert_numeric(
            np.array(["uint64"], dtype=object),
            set(),
            coerce_numeric=True,
            convert_to_masked_nullable=convert_to_masked_nullable,
        )
        if convert_to_masked_nullable:
            result = FloatingArray(*result)
        else:
            result = result[0]
        assert np.isnan(result)

    @pytest.mark.parametrize("value", [-(2**63) - 1, 2**64])
    def test_convert_int_overflow(self, value):
        # see gh-18584
        arr = np.array([value], dtype=object)
        result = lib.maybe_convert_objects(arr)
        tm.assert_numpy_array_equal(arr, result)

    @pytest.mark.parametrize("val", [None, np.nan, float("nan")])
    @pytest.mark.parametrize("dtype", ["M8[ns]", "m8[ns]"])
    def test_maybe_convert_objects_nat_inference(self, val, dtype):
        dtype = np.dtype(dtype)
        vals = np.array([pd.NaT, val], dtype=object)
        result = lib.maybe_convert_objects(
            vals,
            convert_non_numeric=True,
            dtype_if_all_nat=dtype,
        )
        assert result.dtype == dtype
        assert np.isnat(result).all()

        result = lib.maybe_convert_objects(
            vals[::-1],
            convert_non_numeric=True,
            dtype_if_all_nat=dtype,
        )
        assert result.dtype == dtype
        assert np.isnat(result).all()

    @pytest.mark.parametrize(
        "value, expected_dtype",
        [
            # see gh-4471
            ([2**63], np.uint64),
            # NumPy bug: can't compare uint64 to int64, as that
            # results in both casting to float64, so we should
            # make sure that this function is robust against it
            ([np.uint64(2**63)], np.uint64),
            ([2, -1], np.int64),
            ([2**63, -1], object),
            # GH#47294
            ([np.uint8(1)], np.uint8),
            ([np.uint16(1)], np.uint16),
            ([np.uint32(1)], np.uint32),
            ([np.uint64(1)], np.uint64),
            ([np.uint8(2), np.uint16(1)], np.uint16),
            ([np.uint32(2), np.uint16(1)], np.uint32),
            ([np.uint32(2), -1], object),
            ([np.uint32(2), 1], np.uint64),
            ([np.uint32(2), np.int32(1)], object),
        ],
    )
    def test_maybe_convert_objects_uint(self, value, expected_dtype):
        arr = np.array(value, dtype=object)
        exp = np.array(value, dtype=expected_dtype)
        tm.assert_numpy_array_equal(lib.maybe_convert_objects(arr), exp)

    def test_maybe_convert_objects_datetime(self):
        # GH27438
        arr = np.array(
            [np.datetime64("2000-01-01"), np.timedelta64(1, "s")], dtype=object
        )
        exp = arr.copy()
        out = lib.maybe_convert_objects(arr, convert_non_numeric=True)
        tm.assert_numpy_array_equal(out, exp)

        arr = np.array([pd.NaT, np.timedelta64(1, "s")], dtype=object)
        exp = np.array([np.timedelta64("NaT"), np.timedelta64(1, "s")], dtype="m8[ns]")
        out = lib.maybe_convert_objects(arr, convert_non_numeric=True)
        tm.assert_numpy_array_equal(out, exp)

        # with convert_non_numeric=True, the nan is a valid NA value for td64
        arr = np.array([np.timedelta64(1, "s"), np.nan], dtype=object)
        exp = exp[::-1]
        out = lib.maybe_convert_objects(arr, convert_non_numeric=True)
        tm.assert_numpy_array_equal(out, exp)

    def test_maybe_convert_objects_dtype_if_all_nat(self):
        arr = np.array([pd.NaT, pd.NaT], dtype=object)
        out = lib.maybe_convert_objects(arr, convert_non_numeric=True)
        # no dtype_if_all_nat passed -> we dont guess
        tm.assert_numpy_array_equal(out, arr)

        out = lib.maybe_convert_objects(
            arr,
            convert_non_numeric=True,
            dtype_if_all_nat=np.dtype("timedelta64[ns]"),
        )
        exp = np.array(["NaT", "NaT"], dtype="timedelta64[ns]")
        tm.assert_numpy_array_equal(out, exp)

        out = lib.maybe_convert_objects(
            arr,
            convert_non_numeric=True,
            dtype_if_all_nat=np.dtype("datetime64[ns]"),
        )
        exp = np.array(["NaT", "NaT"], dtype="datetime64[ns]")
        tm.assert_numpy_array_equal(out, exp)

    def test_maybe_convert_objects_dtype_if_all_nat_invalid(self):
        # we accept datetime64[ns], timedelta64[ns], and EADtype
        arr = np.array([pd.NaT, pd.NaT], dtype=object)

        with pytest.raises(ValueError, match="int64"):
            lib.maybe_convert_objects(
                arr,
                convert_non_numeric=True,
                dtype_if_all_nat=np.dtype("int64"),
            )

    @pytest.mark.parametrize("dtype", ["datetime64[ns]", "timedelta64[ns]"])
    def test_maybe_convert_objects_datetime_overflow_safe(self, dtype):
        stamp = datetime(2363, 10, 4)  # Enterprise-D launch date
        if dtype == "timedelta64[ns]":
            stamp = stamp - datetime(1970, 1, 1)
        arr = np.array([stamp], dtype=object)

        out = lib.maybe_convert_objects(arr, convert_non_numeric=True)
        # no OutOfBoundsDatetime/OutOfBoundsTimedeltas
        tm.assert_numpy_array_equal(out, arr)

    def test_maybe_convert_objects_mixed_datetimes(self):
        ts = Timestamp("now")
        vals = [ts, ts.to_pydatetime(), ts.to_datetime64(), pd.NaT, np.nan, None]

        for data in itertools.permutations(vals):
            data = np.array(list(data), dtype=object)
            expected = DatetimeIndex(data)._data._ndarray
            result = lib.maybe_convert_objects(data, convert_non_numeric=True)
            tm.assert_numpy_array_equal(result, expected)

    def test_maybe_convert_objects_timedelta64_nat(self):
        obj = np.timedelta64("NaT", "ns")
        arr = np.array([obj], dtype=object)
        assert arr[0] is obj

        result = lib.maybe_convert_objects(arr, convert_non_numeric=True)

        expected = np.array([obj], dtype="m8[ns]")
        tm.assert_numpy_array_equal(result, expected)

    @pytest.mark.parametrize(
        "exp",
        [
            IntegerArray(np.array([2, 0], dtype="i8"), np.array([False, True])),
            IntegerArray(np.array([2, 0], dtype="int64"), np.array([False, True])),
        ],
    )
    def test_maybe_convert_objects_nullable_integer(self, exp):
        # GH27335
        arr = np.array([2, np.nan], dtype=object)
        result = lib.maybe_convert_objects(arr, convert_to_nullable_dtype=True)

        tm.assert_extension_array_equal(result, exp)

    @pytest.mark.parametrize(
        "dtype, val", [("int64", 1), ("uint64", np.iinfo(np.int64).max + 1)]
    )
    def test_maybe_convert_objects_nullable_none(self, dtype, val):
        # GH#50043
        arr = np.array([val, None, 3], dtype="object")
        result = lib.maybe_convert_objects(arr, convert_to_nullable_dtype=True)
        expected = IntegerArray(
            np.array([val, 0, 3], dtype=dtype), np.array([False, True, False])
        )
        tm.assert_extension_array_equal(result, expected)

    @pytest.mark.parametrize(
        "convert_to_masked_nullable, exp",
        [
            (True, IntegerArray(np.array([2, 0], dtype="i8"), np.array([False, True]))),
            (False, np.array([2, np.nan], dtype="float64")),
        ],
    )
    def test_maybe_convert_numeric_nullable_integer(
        self, convert_to_masked_nullable, exp
    ):
        # GH 40687
        arr = np.array([2, np.nan], dtype=object)
        result = lib.maybe_convert_numeric(
            arr, set(), convert_to_masked_nullable=convert_to_masked_nullable
        )
        if convert_to_masked_nullable:
            result = IntegerArray(*result)
            tm.assert_extension_array_equal(result, exp)
        else:
            result = result[0]
            tm.assert_numpy_array_equal(result, exp)

    @pytest.mark.parametrize(
        "convert_to_masked_nullable, exp",
        [
            (
                True,
                FloatingArray(
                    np.array([2.0, 0.0], dtype="float64"), np.array([False, True])
                ),
            ),
            (False, np.array([2.0, np.nan], dtype="float64")),
        ],
    )
    def test_maybe_convert_numeric_floating_array(
        self, convert_to_masked_nullable, exp
    ):
        # GH 40687
        arr = np.array([2.0, np.nan], dtype=object)
        result = lib.maybe_convert_numeric(
            arr, set(), convert_to_masked_nullable=convert_to_masked_nullable
        )
        if convert_to_masked_nullable:
            tm.assert_extension_array_equal(FloatingArray(*result), exp)
        else:
            result = result[0]
            tm.assert_numpy_array_equal(result, exp)

    def test_maybe_convert_objects_bool_nan(self):
        # GH32146
        ind = Index([True, False, np.nan], dtype=object)
        exp = np.array([True, False, np.nan], dtype=object)
        out = lib.maybe_convert_objects(ind.values, safe=1)
        tm.assert_numpy_array_equal(out, exp)

    def test_maybe_convert_objects_nullable_boolean(self):
        # GH50047
        arr = np.array([True, False], dtype=object)
        exp = np.array([True, False])
        out = lib.maybe_convert_objects(arr, convert_to_nullable_dtype=True)
        tm.assert_numpy_array_equal(out, exp)

        arr = np.array([True, False, pd.NaT], dtype=object)
        exp = np.array([True, False, pd.NaT], dtype=object)
        out = lib.maybe_convert_objects(arr, convert_to_nullable_dtype=True)
        tm.assert_numpy_array_equal(out, exp)

    @pytest.mark.parametrize("val", [None, np.nan])
    def test_maybe_convert_objects_nullable_boolean_na(self, val):
        # GH50047
        arr = np.array([True, False, val], dtype=object)
        exp = BooleanArray(
            np.array([True, False, False]), np.array([False, False, True])
        )
        out = lib.maybe_convert_objects(arr, convert_to_nullable_dtype=True)
        tm.assert_extension_array_equal(out, exp)

    @pytest.mark.parametrize(
        "data0",
        [
            True,
            1,
            1.0,
            1.0 + 1.0j,
            np.int8(1),
            np.int16(1),
            np.int32(1),
            np.int64(1),
            np.float16(1),
            np.float32(1),
            np.float64(1),
            np.complex64(1),
            np.complex128(1),
        ],
    )
    @pytest.mark.parametrize(
        "data1",
        [
            True,
            1,
            1.0,
            1.0 + 1.0j,
            np.int8(1),
            np.int16(1),
            np.int32(1),
            np.int64(1),
            np.float16(1),
            np.float32(1),
            np.float64(1),
            np.complex64(1),
            np.complex128(1),
        ],
    )
    def test_maybe_convert_objects_itemsize(self, data0, data1):
        # GH 40908
        data = [data0, data1]
        arr = np.array(data, dtype="object")

        common_kind = np.result_type(type(data0), type(data1)).kind
        kind0 = "python" if not hasattr(data0, "dtype") else data0.dtype.kind
        kind1 = "python" if not hasattr(data1, "dtype") else data1.dtype.kind
        if kind0 != "python" and kind1 != "python":
            kind = common_kind
            itemsize = max(data0.dtype.itemsize, data1.dtype.itemsize)
        elif is_bool(data0) or is_bool(data1):
            kind = "bool" if (is_bool(data0) and is_bool(data1)) else "object"
            itemsize = ""
        elif is_complex(data0) or is_complex(data1):
            kind = common_kind
            itemsize = 16
        else:
            kind = common_kind
            itemsize = 8

        expected = np.array(data, dtype=f"{kind}{itemsize}")
        result = lib.maybe_convert_objects(arr)
        tm.assert_numpy_array_equal(result, expected)

    def test_mixed_dtypes_remain_object_array(self):
        # GH14956
        arr = np.array([datetime(2015, 1, 1, tzinfo=pytz.utc), 1], dtype=object)
        result = lib.maybe_convert_objects(arr, convert_non_numeric=True)
        tm.assert_numpy_array_equal(result, arr)

    @pytest.mark.parametrize(
        "idx",
        [
            pd.IntervalIndex.from_breaks(range(5), closed="both"),
            pd.period_range("2016-01-01", periods=3, freq="D"),
        ],
    )
    def test_maybe_convert_objects_ea(self, idx):
        result = lib.maybe_convert_objects(
            np.array(idx, dtype=object),
            convert_non_numeric=True,
        )
        tm.assert_extension_array_equal(result, idx._data)


class TestTypeInference:
    # Dummy class used for testing with Python objects
    class Dummy:
        pass

    def test_inferred_dtype_fixture(self, any_skipna_inferred_dtype):
        # see pandas/conftest.py
        inferred_dtype, values = any_skipna_inferred_dtype

        # make sure the inferred dtype of the fixture is as requested
        assert inferred_dtype == lib.infer_dtype(values, skipna=True)

    @pytest.mark.parametrize("skipna", [True, False])
    def test_length_zero(self, skipna):
        result = lib.infer_dtype(np.array([], dtype="i4"), skipna=skipna)
        assert result == "integer"

        result = lib.infer_dtype([], skipna=skipna)
        assert result == "empty"

        # GH 18004
        arr = np.array([np.array([], dtype=object), np.array([], dtype=object)])
        result = lib.infer_dtype(arr, skipna=skipna)
        assert result == "empty"

    def test_integers(self):
        arr = np.array([1, 2, 3, np.int64(4), np.int32(5)], dtype="O")
        result = lib.infer_dtype(arr, skipna=True)
        assert result == "integer"

        arr = np.array([1, 2, 3, np.int64(4), np.int32(5), "foo"], dtype="O")
        result = lib.infer_dtype(arr, skipna=True)
        assert result == "mixed-integer"

        arr = np.array([1, 2, 3, 4, 5], dtype="i4")
        result = lib.infer_dtype(arr, skipna=True)
        assert result == "integer"

    @pytest.mark.parametrize(
        "arr, skipna",
        [
            (np.array([1, 2, np.nan, np.nan, 3], dtype="O"), False),
            (np.array([1, 2, np.nan, np.nan, 3], dtype="O"), True),
            (np.array([1, 2, 3, np.int64(4), np.int32(5), np.nan], dtype="O"), False),
            (np.array([1, 2, 3, np.int64(4), np.int32(5), np.nan], dtype="O"), True),
        ],
    )
    def test_integer_na(self, arr, skipna):
        # GH 27392
        result = lib.infer_dtype(arr, skipna=skipna)
        expected = "integer" if skipna else "integer-na"
        assert result == expected

    def test_infer_dtype_skipna_default(self):
        # infer_dtype `skipna` default deprecated in GH#24050,
        #  changed to True in GH#29876
        arr = np.array([1, 2, 3, np.nan], dtype=object)

        result = lib.infer_dtype(arr)
        assert result == "integer"

    def test_bools(self):
        arr = np.array([True, False, True, True, True], dtype="O")
        result = lib.infer_dtype(arr, skipna=True)
        assert result == "boolean"

        arr = np.array([np.bool_(True), np.bool_(False)], dtype="O")
        result = lib.infer_dtype(arr, skipna=True)
        assert result == "boolean"

        arr = np.array([True, False, True, "foo"], dtype="O")
        result = lib.infer_dtype(arr, skipna=True)
        assert result == "mixed"

        arr = np.array([True, False, True], dtype=bool)
        result = lib.infer_dtype(arr, skipna=True)
        assert result == "boolean"

        arr = np.array([True, np.nan, False], dtype="O")
        result = lib.infer_dtype(arr, skipna=True)
        assert result == "boolean"

        result = lib.infer_dtype(arr, skipna=False)
        assert result == "mixed"

    def test_floats(self):
        arr = np.array([1.0, 2.0, 3.0, np.float64(4), np.float32(5)], dtype="O")
        result = lib.infer_dtype(arr, skipna=True)
        assert result == "floating"

        arr = np.array([1, 2, 3, np.float64(4), np.float32(5), "foo"], dtype="O")
        result = lib.infer_dtype(arr, skipna=True)
        assert result == "mixed-integer"

        arr = np.array([1, 2, 3, 4, 5], dtype="f4")
        result = lib.infer_dtype(arr, skipna=True)
        assert result == "floating"

        arr = np.array([1, 2, 3, 4, 5], dtype="f8")
        result = lib.infer_dtype(arr, skipna=True)
        assert result == "floating"

    def test_decimals(self):
        # GH15690
        arr = np.array([Decimal(1), Decimal(2), Decimal(3)])
        result = lib.infer_dtype(arr, skipna=True)
        assert result == "decimal"

        arr = np.array([1.0, 2.0, Decimal(3)])
        result = lib.infer_dtype(arr, skipna=True)
        assert result == "mixed"

        result = lib.infer_dtype(arr[::-1], skipna=True)
        assert result == "mixed"

        arr = np.array([Decimal(1), Decimal("NaN"), Decimal(3)])
        result = lib.infer_dtype(arr, skipna=True)
        assert result == "decimal"

        arr = np.array([Decimal(1), np.nan, Decimal(3)], dtype="O")
        result = lib.infer_dtype(arr, skipna=True)
        assert result == "decimal"

    # complex is compatible with nan, so skipna has no effect
    @pytest.mark.parametrize("skipna", [True, False])
    def test_complex(self, skipna):
        # gets cast to complex on array construction
        arr = np.array([1.0, 2.0, 1 + 1j])
        result = lib.infer_dtype(arr, skipna=skipna)
        assert result == "complex"

        arr = np.array([1.0, 2.0, 1 + 1j], dtype="O")
        result = lib.infer_dtype(arr, skipna=skipna)
        assert result == "mixed"

        result = lib.infer_dtype(arr[::-1], skipna=skipna)
        assert result == "mixed"

        # gets cast to complex on array construction
        arr = np.array([1, np.nan, 1 + 1j])
        result = lib.infer_dtype(arr, skipna=skipna)
        assert result == "complex"

        arr = np.array([1.0, np.nan, 1 + 1j], dtype="O")
        result = lib.infer_dtype(arr, skipna=skipna)
        assert result == "mixed"

        # complex with nans stays complex
        arr = np.array([1 + 1j, np.nan, 3 + 3j], dtype="O")
        result = lib.infer_dtype(arr, skipna=skipna)
        assert result == "complex"

        # test smaller complex dtype; will pass through _try_infer_map fastpath
        arr = np.array([1 + 1j, np.nan, 3 + 3j], dtype=np.complex64)
        result = lib.infer_dtype(arr, skipna=skipna)
        assert result == "complex"

    def test_string(self):
        pass

    def test_unicode(self):
        arr = ["a", np.nan, "c"]
        result = lib.infer_dtype(arr, skipna=False)
        # This currently returns "mixed", but it's not clear that's optimal.
        # This could also return "string" or "mixed-string"
        assert result == "mixed"

        # even though we use skipna, we are only skipping those NAs that are
        #  considered matching by is_string_array
        arr = ["a", np.nan, "c"]
        result = lib.infer_dtype(arr, skipna=True)
        assert result == "string"

        arr = ["a", pd.NA, "c"]
        result = lib.infer_dtype(arr, skipna=True)
        assert result == "string"

        arr = ["a", pd.NaT, "c"]
        result = lib.infer_dtype(arr, skipna=True)
        assert result == "mixed"

        arr = ["a", "c"]
        result = lib.infer_dtype(arr, skipna=False)
        assert result == "string"

    @pytest.mark.parametrize(
        "dtype, missing, skipna, expected",
        [
            (float, np.nan, False, "floating"),
            (float, np.nan, True, "floating"),
            (object, np.nan, False, "floating"),
            (object, np.nan, True, "empty"),
            (object, None, False, "mixed"),
            (object, None, True, "empty"),
        ],
    )
    @pytest.mark.parametrize("box", [Series, np.array])
    def test_object_empty(self, box, missing, dtype, skipna, expected):
        # GH 23421
        arr = box([missing, missing], dtype=dtype)

        result = lib.infer_dtype(arr, skipna=skipna)
        assert result == expected

    def test_datetime(self):
        dates = [datetime(2012, 1, x) for x in range(1, 20)]
        index = Index(dates)
        assert index.inferred_type == "datetime64"

    def test_infer_dtype_datetime64(self):
        arr = np.array(
            [np.datetime64("2011-01-01"), np.datetime64("2011-01-01")], dtype=object
        )
        assert lib.infer_dtype(arr, skipna=True) == "datetime64"

    @pytest.mark.parametrize("na_value", [pd.NaT, np.nan])
    def test_infer_dtype_datetime64_with_na(self, na_value):
        # starts with nan
        arr = np.array([na_value, np.datetime64("2011-01-02")])
        assert lib.infer_dtype(arr, skipna=True) == "datetime64"

        arr = np.array([na_value, np.datetime64("2011-01-02"), na_value])
        assert lib.infer_dtype(arr, skipna=True) == "datetime64"

    @pytest.mark.parametrize(
        "arr",
        [
            np.array(
                [np.timedelta64("nat"), np.datetime64("2011-01-02")], dtype=object
            ),
            np.array(
                [np.datetime64("2011-01-02"), np.timedelta64("nat")], dtype=object
            ),
            np.array([np.datetime64("2011-01-01"), Timestamp("2011-01-02")]),
            np.array([Timestamp("2011-01-02"), np.datetime64("2011-01-01")]),
            np.array([np.nan, Timestamp("2011-01-02"), 1.1]),
            np.array([np.nan, "2011-01-01", Timestamp("2011-01-02")], dtype=object),
            np.array([np.datetime64("nat"), np.timedelta64(1, "D")], dtype=object),
            np.array([np.timedelta64(1, "D"), np.datetime64("nat")], dtype=object),
        ],
    )
    def test_infer_datetimelike_dtype_mixed(self, arr):
        assert lib.infer_dtype(arr, skipna=False) == "mixed"

    def test_infer_dtype_mixed_integer(self):
        arr = np.array([np.nan, Timestamp("2011-01-02"), 1])
        assert lib.infer_dtype(arr, skipna=True) == "mixed-integer"

    @pytest.mark.parametrize(
        "arr",
        [
            np.array([Timestamp("2011-01-01"), Timestamp("2011-01-02")]),
            np.array([datetime(2011, 1, 1), datetime(2012, 2, 1)]),
            np.array([datetime(2011, 1, 1), Timestamp("2011-01-02")]),
        ],
    )
    def test_infer_dtype_datetime(self, arr):
        assert lib.infer_dtype(arr, skipna=True) == "datetime"

    @pytest.mark.parametrize("na_value", [pd.NaT, np.nan])
    @pytest.mark.parametrize(
        "time_stamp", [Timestamp("2011-01-01"), datetime(2011, 1, 1)]
    )
    def test_infer_dtype_datetime_with_na(self, na_value, time_stamp):
        # starts with nan
        arr = np.array([na_value, time_stamp])
        assert lib.infer_dtype(arr, skipna=True) == "datetime"

        arr = np.array([na_value, time_stamp, na_value])
        assert lib.infer_dtype(arr, skipna=True) == "datetime"

    @pytest.mark.parametrize(
        "arr",
        [
            np.array([Timedelta("1 days"), Timedelta("2 days")]),
            np.array([np.timedelta64(1, "D"), np.timedelta64(2, "D")], dtype=object),
            np.array([timedelta(1), timedelta(2)]),
        ],
    )
    def test_infer_dtype_timedelta(self, arr):
        assert lib.infer_dtype(arr, skipna=True) == "timedelta"

    @pytest.mark.parametrize("na_value", [pd.NaT, np.nan])
    @pytest.mark.parametrize(
        "delta", [Timedelta("1 days"), np.timedelta64(1, "D"), timedelta(1)]
    )
    def test_infer_dtype_timedelta_with_na(self, na_value, delta):
        # starts with nan
        arr = np.array([na_value, delta])
        assert lib.infer_dtype(arr, skipna=True) == "timedelta"

        arr = np.array([na_value, delta, na_value])
        assert lib.infer_dtype(arr, skipna=True) == "timedelta"

    def test_infer_dtype_period(self):
        # GH 13664
        arr = np.array([Period("2011-01", freq="D"), Period("2011-02", freq="D")])
        assert lib.infer_dtype(arr, skipna=True) == "period"

        # non-homogeneous freqs -> mixed
        arr = np.array([Period("2011-01", freq="D"), Period("2011-02", freq="M")])
        assert lib.infer_dtype(arr, skipna=True) == "mixed"

    @pytest.mark.parametrize("klass", [pd.array, Series, Index])
    @pytest.mark.parametrize("skipna", [True, False])
    def test_infer_dtype_period_array(self, klass, skipna):
        # https://github.com/pandas-dev/pandas/issues/23553
        values = klass(
            [
                Period("2011-01-01", freq="D"),
                Period("2011-01-02", freq="D"),
                pd.NaT,
            ]
        )
        assert lib.infer_dtype(values, skipna=skipna) == "period"

        # periods but mixed freq
        values = klass(
            [
                Period("2011-01-01", freq="D"),
                Period("2011-01-02", freq="M"),
                pd.NaT,
            ]
        )
        # with pd.array this becomes NumpyExtensionArray which ends up
        #  as "unknown-array"
        exp = "unknown-array" if klass is pd.array else "mixed"
        assert lib.infer_dtype(values, skipna=skipna) == exp

    def test_infer_dtype_period_mixed(self):
        arr = np.array(
            [Period("2011-01", freq="M"), np.datetime64("nat")], dtype=object
        )
        assert lib.infer_dtype(arr, skipna=False) == "mixed"

        arr = np.array(
            [np.datetime64("nat"), Period("2011-01", freq="M")], dtype=object
        )
        assert lib.infer_dtype(arr, skipna=False) == "mixed"

    @pytest.mark.parametrize("na_value", [pd.NaT, np.nan])
    def test_infer_dtype_period_with_na(self, na_value):
        # starts with nan
        arr = np.array([na_value, Period("2011-01", freq="D")])
        assert lib.infer_dtype(arr, skipna=True) == "period"

        arr = np.array([na_value, Period("2011-01", freq="D"), na_value])
        assert lib.infer_dtype(arr, skipna=True) == "period"

    def test_infer_dtype_all_nan_nat_like(self):
        arr = np.array([np.nan, np.nan])
        assert lib.infer_dtype(arr, skipna=True) == "floating"

        # nan and None mix are result in mixed
        arr = np.array([np.nan, np.nan, None])
        assert lib.infer_dtype(arr, skipna=True) == "empty"
        assert lib.infer_dtype(arr, skipna=False) == "mixed"

        arr = np.array([None, np.nan, np.nan])
        assert lib.infer_dtype(arr, skipna=True) == "empty"
        assert lib.infer_dtype(arr, skipna=False) == "mixed"

        # pd.NaT
        arr = np.array([pd.NaT])
        assert lib.infer_dtype(arr, skipna=False) == "datetime"

        arr = np.array([pd.NaT, np.nan])
        assert lib.infer_dtype(arr, skipna=False) == "datetime"

        arr = np.array([np.nan, pd.NaT])
        assert lib.infer_dtype(arr, skipna=False) == "datetime"

        arr = np.array([np.nan, pd.NaT, np.nan])
        assert lib.infer_dtype(arr, skipna=False) == "datetime"

        arr = np.array([None, pd.NaT, None])
        assert lib.infer_dtype(arr, skipna=False) == "datetime"

        # np.datetime64(nat)
        arr = np.array([np.datetime64("nat")])
        assert lib.infer_dtype(arr, skipna=False) == "datetime64"

        for n in [np.nan, pd.NaT, None]:
            arr = np.array([n, np.datetime64("nat"), n])
            assert lib.infer_dtype(arr, skipna=False) == "datetime64"

            arr = np.array([pd.NaT, n, np.datetime64("nat"), n])
            assert lib.infer_dtype(arr, skipna=False) == "datetime64"

        arr = np.array([np.timedelta64("nat")], dtype=object)
        assert lib.infer_dtype(arr, skipna=False) == "timedelta"

        for n in [np.nan, pd.NaT, None]:
            arr = np.array([n, np.timedelta64("nat"), n])
            assert lib.infer_dtype(arr, skipna=False) == "timedelta"

            arr = np.array([pd.NaT, n, np.timedelta64("nat"), n])
            assert lib.infer_dtype(arr, skipna=False) == "timedelta"

        # datetime / timedelta mixed
        arr = np.array([pd.NaT, np.datetime64("nat"), np.timedelta64("nat"), np.nan])
        assert lib.infer_dtype(arr, skipna=False) == "mixed"

        arr = np.array([np.timedelta64("nat"), np.datetime64("nat")], dtype=object)
        assert lib.infer_dtype(arr, skipna=False) == "mixed"

    def test_is_datetimelike_array_all_nan_nat_like(self):
        arr = np.array([np.nan, pd.NaT, np.datetime64("nat")])
        assert lib.is_datetime_array(arr)
        assert lib.is_datetime64_array(arr)
        assert not lib.is_timedelta_or_timedelta64_array(arr)

        arr = np.array([np.nan, pd.NaT, np.timedelta64("nat")])
        assert not lib.is_datetime_array(arr)
        assert not lib.is_datetime64_array(arr)
        assert lib.is_timedelta_or_timedelta64_array(arr)

        arr = np.array([np.nan, pd.NaT, np.datetime64("nat"), np.timedelta64("nat")])
        assert not lib.is_datetime_array(arr)
        assert not lib.is_datetime64_array(arr)
        assert not lib.is_timedelta_or_timedelta64_array(arr)

        arr = np.array([np.nan, pd.NaT])
        assert lib.is_datetime_array(arr)
        assert lib.is_datetime64_array(arr)
        assert lib.is_timedelta_or_timedelta64_array(arr)

        arr = np.array([np.nan, np.nan], dtype=object)
        assert not lib.is_datetime_array(arr)
        assert not lib.is_datetime64_array(arr)
        assert not lib.is_timedelta_or_timedelta64_array(arr)

        assert lib.is_datetime_with_singletz_array(
            np.array(
                [
                    Timestamp("20130101", tz="US/Eastern"),
                    Timestamp("20130102", tz="US/Eastern"),
                ],
                dtype=object,
            )
        )
        assert not lib.is_datetime_with_singletz_array(
            np.array(
                [
                    Timestamp("20130101", tz="US/Eastern"),
                    Timestamp("20130102", tz="CET"),
                ],
                dtype=object,
            )
        )

    @pytest.mark.parametrize(
        "func",
        [
            "is_datetime_array",
            "is_datetime64_array",
            "is_bool_array",
            "is_timedelta_or_timedelta64_array",
            "is_date_array",
            "is_time_array",
            "is_interval_array",
        ],
    )
    def test_other_dtypes_for_array(self, func):
        func = getattr(lib, func)
        arr = np.array(["foo", "bar"])
        assert not func(arr)
        assert not func(arr.reshape(2, 1))

        arr = np.array([1, 2])
        assert not func(arr)
        assert not func(arr.reshape(2, 1))

    def test_date(self):
        dates = [date(2012, 1, day) for day in range(1, 20)]
        index = Index(dates)
        assert index.inferred_type == "date"

        dates = [date(2012, 1, day) for day in range(1, 20)] + [np.nan]
        result = lib.infer_dtype(dates, skipna=False)
        assert result == "mixed"

        result = lib.infer_dtype(dates, skipna=True)
        assert result == "date"

    @pytest.mark.parametrize(
        "values",
        [
            [date(2020, 1, 1), Timestamp("2020-01-01")],
            [Timestamp("2020-01-01"), date(2020, 1, 1)],
            [date(2020, 1, 1), pd.NaT],
            [pd.NaT, date(2020, 1, 1)],
        ],
    )
    @pytest.mark.parametrize("skipna", [True, False])
    def test_infer_dtype_date_order_invariant(self, values, skipna):
        # https://github.com/pandas-dev/pandas/issues/33741
        result = lib.infer_dtype(values, skipna=skipna)
        assert result == "date"

    def test_is_numeric_array(self):
        assert lib.is_float_array(np.array([1, 2.0]))
        assert lib.is_float_array(np.array([1, 2.0, np.nan]))
        assert not lib.is_float_array(np.array([1, 2]))

        assert lib.is_integer_array(np.array([1, 2]))
        assert not lib.is_integer_array(np.array([1, 2.0]))

    def test_is_string_array(self):
        # We should only be accepting pd.NA, np.nan,
        # other floating point nans e.g. float('nan')]
        # when skipna is True.
        assert lib.is_string_array(np.array(["foo", "bar"]))
        assert not lib.is_string_array(
            np.array(["foo", "bar", pd.NA], dtype=object), skipna=False
        )
        assert lib.is_string_array(
            np.array(["foo", "bar", pd.NA], dtype=object), skipna=True
        )
        # we allow NaN/None in the StringArray constructor, so its allowed here
        assert lib.is_string_array(
            np.array(["foo", "bar", None], dtype=object), skipna=True
        )
        assert lib.is_string_array(
            np.array(["foo", "bar", np.nan], dtype=object), skipna=True
        )
        # But not e.g. datetimelike or Decimal NAs
        assert not lib.is_string_array(
            np.array(["foo", "bar", pd.NaT], dtype=object), skipna=True
        )
        assert not lib.is_string_array(
            np.array(["foo", "bar", np.datetime64("NaT")], dtype=object), skipna=True
        )
        assert not lib.is_string_array(
            np.array(["foo", "bar", Decimal("NaN")], dtype=object), skipna=True
        )

        assert not lib.is_string_array(
            np.array(["foo", "bar", None], dtype=object), skipna=False
        )
        assert not lib.is_string_array(
            np.array(["foo", "bar", np.nan], dtype=object), skipna=False
        )
        assert not lib.is_string_array(np.array([1, 2]))

    @pytest.mark.parametrize(
        "func",
        [
            "is_bool_array",
            "is_date_array",
            "is_datetime_array",
            "is_datetime64_array",
            "is_float_array",
            "is_integer_array",
            "is_interval_array",
            "is_string_array",
            "is_time_array",
            "is_timedelta_or_timedelta64_array",
        ],
    )
    def test_is_dtype_array_empty_obj(self, func):
        # https://github.com/pandas-dev/pandas/pull/60796
        func = getattr(lib, func)

        arr = np.empty((2, 0), dtype=object)
        assert not func(arr)

        arr = np.empty((0, 2), dtype=object)
        assert not func(arr)

    def test_to_object_array_tuples(self):
        r = (5, 6)
        values = [r]
        lib.to_object_array_tuples(values)

        # make sure record array works
        record = namedtuple("record", "x y")
        r = record(5, 6)
        values = [r]
        lib.to_object_array_tuples(values)

    def test_object(self):
        # GH 7431
        # cannot infer more than this as only a single element
        arr = np.array([None], dtype="O")
        result = lib.infer_dtype(arr, skipna=False)
        assert result == "mixed"
        result = lib.infer_dtype(arr, skipna=True)
        assert result == "empty"

    def test_to_object_array_width(self):
        # see gh-13320
        rows = [[1, 2, 3], [4, 5, 6]]

        expected = np.array(rows, dtype=object)
        out = lib.to_object_array(rows)
        tm.assert_numpy_array_equal(out, expected)

        expected = np.array(rows, dtype=object)
        out = lib.to_object_array(rows, min_width=1)
        tm.assert_numpy_array_equal(out, expected)

        expected = np.array(
            [[1, 2, 3, None, None], [4, 5, 6, None, None]], dtype=object
        )
        out = lib.to_object_array(rows, min_width=5)
        tm.assert_numpy_array_equal(out, expected)

    def test_is_period(self):
        # GH#55264
        msg = "is_period is deprecated and will be removed in a future version"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert lib.is_period(Period("2011-01", freq="M"))
            assert not lib.is_period(PeriodIndex(["2011-01"], freq="M"))
            assert not lib.is_period(Timestamp("2011-01"))
            assert not lib.is_period(1)
            assert not lib.is_period(np.nan)

    def test_is_interval(self):
        # GH#55264
        msg = "is_interval is deprecated and will be removed in a future version"
        item = Interval(1, 2)
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert lib.is_interval(item)
            assert not lib.is_interval(pd.IntervalIndex([item]))
            assert not lib.is_interval(pd.IntervalIndex([item])._engine)

    def test_categorical(self):
        # GH 8974
        arr = Categorical(list("abc"))
        result = lib.infer_dtype(arr, skipna=True)
        assert result == "categorical"

        result = lib.infer_dtype(Series(arr), skipna=True)
        assert result == "categorical"

        arr = Categorical(list("abc"), categories=["cegfab"], ordered=True)
        result = lib.infer_dtype(arr, skipna=True)
        assert result == "categorical"

        result = lib.infer_dtype(Series(arr), skipna=True)
        assert result == "categorical"

    @pytest.mark.parametrize("asobject", [True, False])
    def test_interval(self, asobject):
        idx = pd.IntervalIndex.from_breaks(range(5), closed="both")
        if asobject:
            idx = idx.astype(object)

        inferred = lib.infer_dtype(idx, skipna=False)
        assert inferred == "interval"

        inferred = lib.infer_dtype(idx._data, skipna=False)
        assert inferred == "interval"

        inferred = lib.infer_dtype(Series(idx, dtype=idx.dtype), skipna=False)
        assert inferred == "interval"

    @pytest.mark.parametrize("value", [Timestamp(0), Timedelta(0), 0, 0.0])
    def test_interval_mismatched_closed(self, value):
        first = Interval(value, value, closed="left")
        second = Interval(value, value, closed="right")

        # if closed match, we should infer "interval"
        arr = np.array([first, first], dtype=object)
        assert lib.infer_dtype(arr, skipna=False) == "interval"

        # if closed dont match, we should _not_ get "interval"
        arr2 = np.array([first, second], dtype=object)
        assert lib.infer_dtype(arr2, skipna=False) == "mixed"

    def test_interval_mismatched_subtype(self):
        first = Interval(0, 1, closed="left")
        second = Interval(Timestamp(0), Timestamp(1), closed="left")
        third = Interval(Timedelta(0), Timedelta(1), closed="left")

        arr = np.array([first, second])
        assert lib.infer_dtype(arr, skipna=False) == "mixed"

        arr = np.array([second, third])
        assert lib.infer_dtype(arr, skipna=False) == "mixed"

        arr = np.array([first, third])
        assert lib.infer_dtype(arr, skipna=False) == "mixed"

        # float vs int subdtype are compatible
        flt_interval = Interval(1.5, 2.5, closed="left")
        arr = np.array([first, flt_interval], dtype=object)
        assert lib.infer_dtype(arr, skipna=False) == "interval"

    @pytest.mark.parametrize("klass", [pd.array, Series])
    @pytest.mark.parametrize("skipna", [True, False])
    @pytest.mark.parametrize("data", [["a", "b", "c"], ["a", "b", pd.NA]])
    def test_string_dtype(self, data, skipna, klass, nullable_string_dtype):
        # StringArray
        val = klass(data, dtype=nullable_string_dtype)
        inferred = lib.infer_dtype(val, skipna=skipna)
        assert inferred == "string"

    @pytest.mark.parametrize("klass", [pd.array, Series])
    @pytest.mark.parametrize("skipna", [True, False])
    @pytest.mark.parametrize("data", [[True, False, True], [True, False, pd.NA]])
    def test_boolean_dtype(self, data, skipna, klass):
        # BooleanArray
        val = klass(data, dtype="boolean")
        inferred = lib.infer_dtype(val, skipna=skipna)
        assert inferred == "boolean"


class TestNumberScalar:
    def test_is_number(self):
        assert is_number(True)
        assert is_number(1)
        assert is_number(1.1)
        assert is_number(1 + 3j)
        assert is_number(np.int64(1))
        assert is_number(np.float64(1.1))
        assert is_number(np.complex128(1 + 3j))
        assert is_number(np.nan)

        assert not is_number(None)
        assert not is_number("x")
        assert not is_number(datetime(2011, 1, 1))
        assert not is_number(np.datetime64("2011-01-01"))
        assert not is_number(Timestamp("2011-01-01"))
        assert not is_number(Timestamp("2011-01-01", tz="US/Eastern"))
        assert not is_number(timedelta(1000))
        assert not is_number(Timedelta("1 days"))

        # questionable
        assert not is_number(np.bool_(False))
        assert is_number(np.timedelta64(1, "D"))

    def test_is_bool(self):
        assert is_bool(True)
        assert is_bool(False)
        assert is_bool(np.bool_(False))

        assert not is_bool(1)
        assert not is_bool(1.1)
        assert not is_bool(1 + 3j)
        assert not is_bool(np.int64(1))
        assert not is_bool(np.float64(1.1))
        assert not is_bool(np.complex128(1 + 3j))
        assert not is_bool(np.nan)
        assert not is_bool(None)
        assert not is_bool("x")
        assert not is_bool(datetime(2011, 1, 1))
        assert not is_bool(np.datetime64("2011-01-01"))
        assert not is_bool(Timestamp("2011-01-01"))
        assert not is_bool(Timestamp("2011-01-01", tz="US/Eastern"))
        assert not is_bool(timedelta(1000))
        assert not is_bool(np.timedelta64(1, "D"))
        assert not is_bool(Timedelta("1 days"))

    def test_is_integer(self):
        assert is_integer(1)
        assert is_integer(np.int64(1))

        assert not is_integer(True)
        assert not is_integer(1.1)
        assert not is_integer(1 + 3j)
        assert not is_integer(False)
        assert not is_integer(np.bool_(False))
        assert not is_integer(np.float64(1.1))
        assert not is_integer(np.complex128(1 + 3j))
        assert not is_integer(np.nan)
        assert not is_integer(None)
        assert not is_integer("x")
        assert not is_integer(datetime(2011, 1, 1))
        assert not is_integer(np.datetime64("2011-01-01"))
        assert not is_integer(Timestamp("2011-01-01"))
        assert not is_integer(Timestamp("2011-01-01", tz="US/Eastern"))
        assert not is_integer(timedelta(1000))
        assert not is_integer(Timedelta("1 days"))
        assert not is_integer(np.timedelta64(1, "D"))

    def test_is_float(self):
        assert is_float(1.1)
        assert is_float(np.float64(1.1))
        assert is_float(np.nan)

        assert not is_float(True)
        assert not is_float(1)
        assert not is_float(1 + 3j)
        assert not is_float(False)
        assert not is_float(np.bool_(False))
        assert not is_float(np.int64(1))
        assert not is_float(np.complex128(1 + 3j))
        assert not is_float(None)
        assert not is_float("x")
        assert not is_float(datetime(2011, 1, 1))
        assert not is_float(np.datetime64("2011-01-01"))
        assert not is_float(Timestamp("2011-01-01"))
        assert not is_float(Timestamp("2011-01-01", tz="US/Eastern"))
        assert not is_float(timedelta(1000))
        assert not is_float(np.timedelta64(1, "D"))
        assert not is_float(Timedelta("1 days"))

    def test_is_datetime_dtypes(self):
        ts = pd.date_range("20130101", periods=3)
        tsa = pd.date_range("20130101", periods=3, tz="US/Eastern")

        msg = "is_datetime64tz_dtype is deprecated"

        assert is_datetime64_dtype("datetime64")
        assert is_datetime64_dtype("datetime64[ns]")
        assert is_datetime64_dtype(ts)
        assert not is_datetime64_dtype(tsa)

        assert not is_datetime64_ns_dtype("datetime64")
        assert is_datetime64_ns_dtype("datetime64[ns]")
        assert is_datetime64_ns_dtype(ts)
        assert is_datetime64_ns_dtype(tsa)

        assert is_datetime64_any_dtype("datetime64")
        assert is_datetime64_any_dtype("datetime64[ns]")
        assert is_datetime64_any_dtype(ts)
        assert is_datetime64_any_dtype(tsa)

        with tm.assert_produces_warning(DeprecationWarning, match=msg):
            assert not is_datetime64tz_dtype("datetime64")
            assert not is_datetime64tz_dtype("datetime64[ns]")
            assert not is_datetime64tz_dtype(ts)
            assert is_datetime64tz_dtype(tsa)

    @pytest.mark.parametrize("tz", ["US/Eastern", "UTC"])
    def test_is_datetime_dtypes_with_tz(self, tz):
        dtype = f"datetime64[ns, {tz}]"
        assert not is_datetime64_dtype(dtype)

        msg = "is_datetime64tz_dtype is deprecated"
        with tm.assert_produces_warning(DeprecationWarning, match=msg):
            assert is_datetime64tz_dtype(dtype)
        assert is_datetime64_ns_dtype(dtype)
        assert is_datetime64_any_dtype(dtype)

    def test_is_timedelta(self):
        assert is_timedelta64_dtype("timedelta64")
        assert is_timedelta64_dtype("timedelta64[ns]")
        assert not is_timedelta64_ns_dtype("timedelta64")
        assert is_timedelta64_ns_dtype("timedelta64[ns]")

        tdi = TimedeltaIndex([1e14, 2e14], dtype="timedelta64[ns]")
        assert is_timedelta64_dtype(tdi)
        assert is_timedelta64_ns_dtype(tdi)
        assert is_timedelta64_ns_dtype(tdi.astype("timedelta64[ns]"))

        assert not is_timedelta64_ns_dtype(Index([], dtype=np.float64))
        assert not is_timedelta64_ns_dtype(Index([], dtype=np.int64))


class TestIsScalar:
    def test_is_scalar_builtin_scalars(self):
        assert is_scalar(None)
        assert is_scalar(True)
        assert is_scalar(False)
        assert is_scalar(Fraction())
        assert is_scalar(0.0)
        assert is_scalar(1)
        assert is_scalar(complex(2))
        assert is_scalar(float("NaN"))
        assert is_scalar(np.nan)
        assert is_scalar("foobar")
        assert is_scalar(b"foobar")
        assert is_scalar(datetime(2014, 1, 1))
        assert is_scalar(date(2014, 1, 1))
        assert is_scalar(time(12, 0))
        assert is_scalar(timedelta(hours=1))
        assert is_scalar(pd.NaT)
        assert is_scalar(pd.NA)

    def test_is_scalar_builtin_nonscalars(self):
        assert not is_scalar({})
        assert not is_scalar([])
        assert not is_scalar([1])
        assert not is_scalar(())
        assert not is_scalar((1,))
        assert not is_scalar(slice(None))
        assert not is_scalar(Ellipsis)

    def test_is_scalar_numpy_array_scalars(self):
        assert is_scalar(np.int64(1))
        assert is_scalar(np.float64(1.0))
        assert is_scalar(np.int32(1))
        assert is_scalar(np.complex64(2))
        assert is_scalar(np.object_("foobar"))
        assert is_scalar(np.str_("foobar"))
        assert is_scalar(np.bytes_(b"foobar"))
        assert is_scalar(np.datetime64("2014-01-01"))
        assert is_scalar(np.timedelta64(1, "h"))

    @pytest.mark.parametrize(
        "zerodim",
        [
            np.array(1),
            np.array("foobar"),
            np.array(np.datetime64("2014-01-01")),
            np.array(np.timedelta64(1, "h")),
            np.array(np.datetime64("NaT")),
        ],
    )
    def test_is_scalar_numpy_zerodim_arrays(self, zerodim):
        assert not is_scalar(zerodim)
        assert is_scalar(lib.item_from_zerodim(zerodim))

    @pytest.mark.parametrize("arr", [np.array([]), np.array([[]])])
    def test_is_scalar_numpy_arrays(self, arr):
        assert not is_scalar(arr)
        assert not is_scalar(MockNumpyLikeArray(arr))

    def test_is_scalar_pandas_scalars(self):
        assert is_scalar(Timestamp("2014-01-01"))
        assert is_scalar(Timedelta(hours=1))
        assert is_scalar(Period("2014-01-01"))
        assert is_scalar(Interval(left=0, right=1))
        assert is_scalar(DateOffset(days=1))
        assert is_scalar(pd.offsets.Minute(3))

    def test_is_scalar_pandas_containers(self):
        assert not is_scalar(Series(dtype=object))
        assert not is_scalar(Series([1]))
        assert not is_scalar(DataFrame())
        assert not is_scalar(DataFrame([[1]]))
        assert not is_scalar(Index([]))
        assert not is_scalar(Index([1]))
        assert not is_scalar(Categorical([]))
        assert not is_scalar(DatetimeIndex([])._data)
        assert not is_scalar(TimedeltaIndex([])._data)
        assert not is_scalar(DatetimeIndex([])._data.to_period("D"))
        assert not is_scalar(pd.array([1, 2, 3]))

    def test_is_scalar_number(self):
        # Number() is not recognied by PyNumber_Check, so by extension
        #  is not recognized by is_scalar, but instances of non-abstract
        #  subclasses are.

        class Numeric(Number):
            def __init__(self, value) -> None:
                self.value = value

            def __int__(self) -> int:
                return self.value

        num = Numeric(1)
        assert is_scalar(num)


@pytest.mark.parametrize("unit", ["ms", "us", "ns"])
def test_datetimeindex_from_empty_datetime64_array(unit):
    idx = DatetimeIndex(np.array([], dtype=f"datetime64[{unit}]"))
    assert len(idx) == 0


def test_nan_to_nat_conversions():
    df = DataFrame(
        {"A": np.asarray(range(10), dtype="float64"), "B": Timestamp("20010101")}
    )
    df.iloc[3:6, :] = np.nan
    result = df.loc[4, "B"]
    assert result is pd.NaT

    s = df["B"].copy()
    s[8:9] = np.nan
    assert s[8] is pd.NaT


@pytest.mark.filterwarnings("ignore::PendingDeprecationWarning")
def test_is_scipy_sparse(spmatrix):
    pytest.importorskip("scipy")
    assert is_scipy_sparse(spmatrix([[0, 1]]))
    assert not is_scipy_sparse(np.array([1]))


def test_ensure_int32():
    values = np.arange(10, dtype=np.int32)
    result = ensure_int32(values)
    assert result.dtype == np.int32

    values = np.arange(10, dtype=np.int64)
    result = ensure_int32(values)
    assert result.dtype == np.int32


@pytest.mark.parametrize(
    "right,result",
    [
        (0, np.uint8),
        (-1, np.int16),
        (300, np.uint16),
        # For floats, we just upcast directly to float64 instead of trying to
        # find a smaller floating dtype
        (300.0, np.uint16),  # for integer floats, we convert them to ints
        (300.1, np.float64),
        (np.int16(300), np.int16 if np_version_gt2 else np.uint16),
    ],
)
def test_find_result_type_uint_int(right, result):
    left_dtype = np.dtype("uint8")
    assert find_result_type(left_dtype, right) == result


@pytest.mark.parametrize(
    "right,result",
    [
        (0, np.int8),
        (-1, np.int8),
        (300, np.int16),
        # For floats, we just upcast directly to float64 instead of trying to
        # find a smaller floating dtype
        (300.0, np.int16),  # for integer floats, we convert them to ints
        (300.1, np.float64),
        (np.int16(300), np.int16),
    ],
)
def test_find_result_type_int_int(right, result):
    left_dtype = np.dtype("int8")
    assert find_result_type(left_dtype, right) == result


@pytest.mark.parametrize(
    "right,result",
    [
        (300.0, np.float64),
        (np.float32(300), np.float32),
    ],
)
def test_find_result_type_floats(right, result):
    left_dtype = np.dtype("float16")
    assert find_result_type(left_dtype, right) == result
