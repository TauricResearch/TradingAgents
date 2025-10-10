import numpy as np
import pytest

import pandas as pd
from pandas import (
    Index,
    Series,
)
import pandas._testing as tm


class TestFloatNumericIndex:
    @pytest.fixture(params=[np.float64, np.float32])
    def dtype(self, request):
        return request.param

    @pytest.fixture
    def simple_index(self, dtype):
        values = np.arange(5, dtype=dtype)
        return Index(values)

    @pytest.fixture(
        params=[
            [1.5, 2, 3, 4, 5],
            [0.0, 2.5, 5.0, 7.5, 10.0],
            [5, 4, 3, 2, 1.5],
            [10.0, 7.5, 5.0, 2.5, 0.0],
        ],
        ids=["mixed", "float", "mixed_dec", "float_dec"],
    )
    def index(self, request, dtype):
        return Index(request.param, dtype=dtype)

    @pytest.fixture
    def mixed_index(self, dtype):
        return Index([1.5, 2, 3, 4, 5], dtype=dtype)

    @pytest.fixture
    def float_index(self, dtype):
        return Index([0.0, 2.5, 5.0, 7.5, 10.0], dtype=dtype)

    def test_repr_roundtrip(self, index):
        tm.assert_index_equal(eval(repr(index)), index, exact=True)

    def check_coerce(self, a, b, is_float_index=True):
        assert a.equals(b)
        tm.assert_index_equal(a, b, exact=False)
        if is_float_index:
            assert isinstance(b, Index)
        else:
            assert type(b) is Index

    def test_constructor_from_list_no_dtype(self):
        index = Index([1.5, 2.5, 3.5])
        assert index.dtype == np.float64

    def test_constructor(self, dtype):
        index_cls = Index

        # explicit construction
        index = index_cls([1, 2, 3, 4, 5], dtype=dtype)

        assert isinstance(index, index_cls)
        assert index.dtype == dtype

        expected = np.array([1, 2, 3, 4, 5], dtype=dtype)
        tm.assert_numpy_array_equal(index.values, expected)

        index = index_cls(np.array([1, 2, 3, 4, 5]), dtype=dtype)
        assert isinstance(index, index_cls)
        assert index.dtype == dtype

        index = index_cls([1.0, 2, 3, 4, 5], dtype=dtype)
        assert isinstance(index, index_cls)
        assert index.dtype == dtype

        index = index_cls(np.array([1.0, 2, 3, 4, 5]), dtype=dtype)
        assert isinstance(index, index_cls)
        assert index.dtype == dtype

        index = index_cls([1.0, 2, 3, 4, 5], dtype=dtype)
        assert isinstance(index, index_cls)
        assert index.dtype == dtype

        index = index_cls(np.array([1.0, 2, 3, 4, 5]), dtype=dtype)
        assert isinstance(index, index_cls)
        assert index.dtype == dtype

        # nan handling
        result = index_cls([np.nan, np.nan], dtype=dtype)
        assert pd.isna(result.values).all()

        result = index_cls(np.array([np.nan]), dtype=dtype)
        assert pd.isna(result.values).all()

    def test_constructor_invalid(self):
        index_cls = Index
        cls_name = index_cls.__name__
        # invalid
        msg = (
            rf"{cls_name}\(\.\.\.\) must be called with a collection of "
            r"some kind, 0\.0 was passed"
        )
        with pytest.raises(TypeError, match=msg):
            index_cls(0.0)

    def test_constructor_coerce(self, mixed_index, float_index):
        self.check_coerce(mixed_index, Index([1.5, 2, 3, 4, 5]))
        self.check_coerce(float_index, Index(np.arange(5) * 2.5))

        result = Index(np.array(np.arange(5) * 2.5, dtype=object))
        assert result.dtype == object  # as of 2.0 to match Series
        self.check_coerce(float_index, result.astype("float64"))

    def test_constructor_explicit(self, mixed_index, float_index):
        # these don't auto convert
        self.check_coerce(
            float_index, Index((np.arange(5) * 2.5), dtype=object), is_float_index=False
        )
        self.check_coerce(
            mixed_index, Index([1.5, 2, 3, 4, 5], dtype=object), is_float_index=False
        )

    def test_type_coercion_fail(self, any_int_numpy_dtype):
        # see gh-15832
        msg = "Trying to coerce float values to integers"
        with pytest.raises(ValueError, match=msg):
            Index([1, 2, 3.5], dtype=any_int_numpy_dtype)

    def test_equals_numeric(self):
        index_cls = Index

        idx = index_cls([1.0, 2.0])
        assert idx.equals(idx)
        assert idx.identical(idx)

        idx2 = index_cls([1.0, 2.0])
        assert idx.equals(idx2)

        idx = index_cls([1.0, np.nan])
        assert idx.equals(idx)
        assert idx.identical(idx)

        idx2 = index_cls([1.0, np.nan])
        assert idx.equals(idx2)

    @pytest.mark.parametrize(
        "other",
        (
            Index([1, 2], dtype=np.int64),
            Index([1.0, 2.0], dtype=object),
            Index([1, 2], dtype=object),
        ),
    )
    def test_equals_numeric_other_index_type(self, other):
        idx = Index([1.0, 2.0])
        assert idx.equals(other)
        assert other.equals(idx)

    @pytest.mark.parametrize(
        "vals",
        [
            pd.date_range("2016-01-01", periods=3),
            pd.timedelta_range("1 Day", periods=3),
        ],
    )
    def test_lookups_datetimelike_values(self, vals, dtype):
        # If we have datetime64 or timedelta64 values, make sure they are
        #  wrapped correctly  GH#31163
        ser = Series(vals, index=range(3, 6))
        ser.index = ser.index.astype(dtype)

        expected = vals[1]

        result = ser[4.0]
        assert isinstance(result, type(expected)) and result == expected
        result = ser[4]
        assert isinstance(result, type(expected)) and result == expected

        result = ser.loc[4.0]
        assert isinstance(result, type(expected)) and result == expected
        result = ser.loc[4]
        assert isinstance(result, type(expected)) and result == expected

        result = ser.at[4.0]
        assert isinstance(result, type(expected)) and result == expected
        # GH#31329 .at[4] should cast to 4.0, matching .loc behavior
        result = ser.at[4]
        assert isinstance(result, type(expected)) and result == expected

        result = ser.iloc[1]
        assert isinstance(result, type(expected)) and result == expected

        result = ser.iat[1]
        assert isinstance(result, type(expected)) and result == expected

    def test_doesnt_contain_all_the_things(self):
        idx = Index([np.nan])
        assert not idx.isin([0]).item()
        assert not idx.isin([1]).item()
        assert idx.isin([np.nan]).item()

    def test_nan_multiple_containment(self):
        index_cls = Index

        idx = index_cls([1.0, np.nan])
        tm.assert_numpy_array_equal(idx.isin([1.0]), np.array([True, False]))
        tm.assert_numpy_array_equal(idx.isin([2.0, np.pi]), np.array([False, False]))
        tm.assert_numpy_array_equal(idx.isin([np.nan]), np.array([False, True]))
        tm.assert_numpy_array_equal(idx.isin([1.0, np.nan]), np.array([True, True]))
        idx = index_cls([1.0, 2.0])
        tm.assert_numpy_array_equal(idx.isin([np.nan]), np.array([False, False]))

    def test_fillna_float64(self):
        index_cls = Index
        # GH 11343
        idx = Index([1.0, np.nan, 3.0], dtype=float, name="x")
        # can't downcast
        exp = Index([1.0, 0.1, 3.0], name="x")
        tm.assert_index_equal(idx.fillna(0.1), exp, exact=True)

        # downcast
        exp = index_cls([1.0, 2.0, 3.0], name="x")
        tm.assert_index_equal(idx.fillna(2), exp)

        # object
        exp = Index([1.0, "obj", 3.0], name="x")
        tm.assert_index_equal(idx.fillna("obj"), exp, exact=True)

    def test_logical_compat(self, simple_index):
        idx = simple_index
        assert idx.all() == idx.values.all()
        assert idx.any() == idx.values.any()

        assert idx.all() == idx.to_series().all()
        assert idx.any() == idx.to_series().any()


class TestNumericInt:
    @pytest.fixture(params=[np.int64, np.int32, np.int16, np.int8, np.uint64])
    def dtype(self, request):
        return request.param

    @pytest.fixture
    def simple_index(self, dtype):
        return Index(range(0, 20, 2), dtype=dtype)

    def test_is_monotonic(self):
        index_cls = Index

        index = index_cls([1, 2, 3, 4])
        assert index.is_monotonic_increasing is True
        assert index.is_monotonic_increasing is True
        assert index._is_strictly_monotonic_increasing is True
        assert index.is_monotonic_decreasing is False
        assert index._is_strictly_monotonic_decreasing is False

        index = index_cls([4, 3, 2, 1])
        assert index.is_monotonic_increasing is False
        assert index._is_strictly_monotonic_increasing is False
        assert index._is_strictly_monotonic_decreasing is True

        index = index_cls([1])
        assert index.is_monotonic_increasing is True
        assert index.is_monotonic_increasing is True
        assert index.is_monotonic_decreasing is True
        assert index._is_strictly_monotonic_increasing is True
        assert index._is_strictly_monotonic_decreasing is True

    def test_is_strictly_monotonic(self):
        index_cls = Index

        index = index_cls([1, 1, 2, 3])
        assert index.is_monotonic_increasing is True
        assert index._is_strictly_monotonic_increasing is False

        index = index_cls([3, 2, 1, 1])
        assert index.is_monotonic_decreasing is True
        assert index._is_strictly_monotonic_decreasing is False

        index = index_cls([1, 1])
        assert index.is_monotonic_increasing
        assert index.is_monotonic_decreasing
        assert not index._is_strictly_monotonic_increasing
        assert not index._is_strictly_monotonic_decreasing

    def test_logical_compat(self, simple_index):
        idx = simple_index
        assert idx.all() == idx.values.all()
        assert idx.any() == idx.values.any()

    def test_identical(self, simple_index, dtype):
        index = simple_index

        idx = Index(index.copy())
        assert idx.identical(index)

        same_values_different_type = Index(idx, dtype=object)
        assert not idx.identical(same_values_different_type)

        idx = index.astype(dtype=object)
        idx = idx.rename("foo")
        same_values = Index(idx, dtype=object)
        assert same_values.identical(idx)

        assert not idx.identical(index)
        assert Index(same_values, name="foo", dtype=object).identical(idx)

        assert not index.astype(dtype=object).identical(index.astype(dtype=dtype))

    def test_cant_or_shouldnt_cast(self, dtype):
        msg = r"invalid literal for int\(\) with base 10: 'foo'"

        # can't
        data = ["foo", "bar", "baz"]
        with pytest.raises(ValueError, match=msg):
            Index(data, dtype=dtype)

    def test_view_index(self, simple_index):
        index = simple_index
        msg = "Passing a type in .*Index.view is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            index.view(Index)

    def test_prevent_casting(self, simple_index):
        index = simple_index
        result = index.astype("O")
        assert result.dtype == np.object_


class TestIntNumericIndex:
    @pytest.fixture(params=[np.int64, np.int32, np.int16, np.int8])
    def dtype(self, request):
        return request.param

    def test_constructor_from_list_no_dtype(self):
        index = Index([1, 2, 3])
        assert index.dtype == np.int64

    def test_constructor(self, dtype):
        index_cls = Index

        # scalar raise Exception
        msg = (
            rf"{index_cls.__name__}\(\.\.\.\) must be called with a collection of some "
            "kind, 5 was passed"
        )
        with pytest.raises(TypeError, match=msg):
            index_cls(5)

        # copy
        # pass list, coerce fine
        index = index_cls([-5, 0, 1, 2], dtype=dtype)
        arr = index.values.copy()
        new_index = index_cls(arr, copy=True)
        tm.assert_index_equal(new_index, index, exact=True)
        val = int(arr[0]) + 3000

        # this should not change index
        if dtype != np.int8:
            # NEP 50 won't allow assignment that would overflow
            arr[0] = val
            assert new_index[0] != val

        if dtype == np.int64:
            # pass list, coerce fine
            index = index_cls([-5, 0, 1, 2], dtype=dtype)
            expected = Index([-5, 0, 1, 2], dtype=dtype)
            tm.assert_index_equal(index, expected)

            # from iterable
            index = index_cls(iter([-5, 0, 1, 2]), dtype=dtype)
            expected = index_cls([-5, 0, 1, 2], dtype=dtype)
            tm.assert_index_equal(index, expected, exact=True)

            # interpret list-like
            expected = index_cls([5, 0], dtype=dtype)
            for cls in [Index, index_cls]:
                for idx in [
                    cls([5, 0], dtype=dtype),
                    cls(np.array([5, 0]), dtype=dtype),
                    cls(Series([5, 0]), dtype=dtype),
                ]:
                    tm.assert_index_equal(idx, expected)

    def test_constructor_corner(self, dtype):
        index_cls = Index

        arr = np.array([1, 2, 3, 4], dtype=object)

        index = index_cls(arr, dtype=dtype)
        assert index.values.dtype == index.dtype
        if dtype == np.int64:
            without_dtype = Index(arr)
            # as of 2.0 we do not infer a dtype when we get an object-dtype
            #  ndarray of numbers, matching Series behavior
            assert without_dtype.dtype == object

            tm.assert_index_equal(index, without_dtype.astype(np.int64))

        # preventing casting
        arr = np.array([1, "2", 3, "4"], dtype=object)
        msg = "Trying to coerce float values to integers"
        with pytest.raises(ValueError, match=msg):
            index_cls(arr, dtype=dtype)

    def test_constructor_coercion_signed_to_unsigned(
        self,
        any_unsigned_int_numpy_dtype,
    ):
        # see gh-15832
        msg = "|".join(
            [
                "Trying to coerce negative values to unsigned integers",
                "The elements provided in the data cannot all be casted",
            ]
        )
        with pytest.raises(OverflowError, match=msg):
            Index([-1], dtype=any_unsigned_int_numpy_dtype)

    def test_constructor_np_signed(self, any_signed_int_numpy_dtype):
        # GH#47475
        scalar = np.dtype(any_signed_int_numpy_dtype).type(1)
        result = Index([scalar])
        expected = Index([1], dtype=any_signed_int_numpy_dtype)
        tm.assert_index_equal(result, expected, exact=True)

    def test_constructor_np_unsigned(self, any_unsigned_int_numpy_dtype):
        # GH#47475
        scalar = np.dtype(any_unsigned_int_numpy_dtype).type(1)
        result = Index([scalar])
        expected = Index([1], dtype=any_unsigned_int_numpy_dtype)
        tm.assert_index_equal(result, expected, exact=True)

    def test_coerce_list(self):
        # coerce things
        arr = Index([1, 2, 3, 4])
        assert isinstance(arr, Index)

        # but not if explicit dtype passed
        arr = Index([1, 2, 3, 4], dtype=object)
        assert type(arr) is Index


class TestFloat16Index:
    # float 16 indexes not supported
    # GH 49535
    def test_constructor(self):
        index_cls = Index
        dtype = np.float16

        msg = "float16 indexes are not supported"

        # explicit construction
        with pytest.raises(NotImplementedError, match=msg):
            index_cls([1, 2, 3, 4, 5], dtype=dtype)

        with pytest.raises(NotImplementedError, match=msg):
            index_cls(np.array([1, 2, 3, 4, 5]), dtype=dtype)

        with pytest.raises(NotImplementedError, match=msg):
            index_cls([1.0, 2, 3, 4, 5], dtype=dtype)

        with pytest.raises(NotImplementedError, match=msg):
            index_cls(np.array([1.0, 2, 3, 4, 5]), dtype=dtype)

        with pytest.raises(NotImplementedError, match=msg):
            index_cls([1.0, 2, 3, 4, 5], dtype=dtype)

        with pytest.raises(NotImplementedError, match=msg):
            index_cls(np.array([1.0, 2, 3, 4, 5]), dtype=dtype)

        # nan handling
        with pytest.raises(NotImplementedError, match=msg):
            index_cls([np.nan, np.nan], dtype=dtype)

        with pytest.raises(NotImplementedError, match=msg):
            index_cls(np.array([np.nan]), dtype=dtype)


@pytest.mark.parametrize(
    "box",
    [list, lambda x: np.array(x, dtype=object), lambda x: Index(x, dtype=object)],
)
def test_uint_index_does_not_convert_to_float64(box):
    # https://github.com/pandas-dev/pandas/issues/28279
    # https://github.com/pandas-dev/pandas/issues/28023
    series = Series(
        [0, 1, 2, 3, 4, 5],
        index=[
            7606741985629028552,
            17876870360202815256,
            17876870360202815256,
            13106359306506049338,
            8991270399732411471,
            8991270399732411472,
        ],
    )

    result = series.loc[box([7606741985629028552, 17876870360202815256])]

    expected = Index(
        [7606741985629028552, 17876870360202815256, 17876870360202815256],
        dtype="uint64",
    )
    tm.assert_index_equal(result.index, expected)

    tm.assert_equal(result, series.iloc[:3])


def test_float64_index_equals():
    # https://github.com/pandas-dev/pandas/issues/35217
    float_index = Index([1.0, 2, 3])
    string_index = Index(["1", "2", "3"])

    result = float_index.equals(string_index)
    assert result is False

    result = string_index.equals(float_index)
    assert result is False


def test_map_dtype_inference_unsigned_to_signed():
    # GH#44609 cases where we don't retain dtype
    idx = Index([1, 2, 3], dtype=np.uint64)
    result = idx.map(lambda x: -x)
    expected = Index([-1, -2, -3], dtype=np.int64)
    tm.assert_index_equal(result, expected)


def test_map_dtype_inference_overflows():
    # GH#44609 case where we have to upcast
    idx = Index(np.array([1, 2, 3], dtype=np.int8))
    result = idx.map(lambda x: x * 1000)
    # TODO: we could plausibly try to infer down to int16 here
    expected = Index([1000, 2000, 3000], dtype=np.int64)
    tm.assert_index_equal(result, expected)


def test_view_to_datetimelike():
    # GH#55710
    idx = Index([1, 2, 3])
    res = idx.view("m8[s]")
    expected = pd.TimedeltaIndex(idx.values.view("m8[s]"))
    tm.assert_index_equal(res, expected)

    res2 = idx.view("m8[D]")
    expected2 = idx.values.view("m8[D]")
    tm.assert_numpy_array_equal(res2, expected2)

    res3 = idx.view("M8[h]")
    expected3 = idx.values.view("M8[h]")
    tm.assert_numpy_array_equal(res3, expected3)
