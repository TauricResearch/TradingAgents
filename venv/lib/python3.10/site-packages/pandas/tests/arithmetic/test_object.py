# Arithmetic tests for DataFrame/Series/Index/Array classes that should
# behave identically.
# Specifically for object dtype
import datetime
from decimal import Decimal
import operator

import numpy as np
import pytest

import pandas.util._test_decorators as td

import pandas as pd
from pandas import (
    Series,
    Timestamp,
    option_context,
)
import pandas._testing as tm
from pandas.core import ops

# ------------------------------------------------------------------
# Comparisons


class TestObjectComparisons:
    def test_comparison_object_numeric_nas(self, comparison_op):
        ser = Series(np.random.default_rng(2).standard_normal(10), dtype=object)
        shifted = ser.shift(2)

        func = comparison_op

        result = func(ser, shifted)
        expected = func(ser.astype(float), shifted.astype(float))
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "infer_string", [False, pytest.param(True, marks=td.skip_if_no("pyarrow"))]
    )
    def test_object_comparisons(self, infer_string):
        with option_context("future.infer_string", infer_string):
            ser = Series(["a", "b", np.nan, "c", "a"])

            result = ser == "a"
            expected = Series([True, False, False, False, True])
            tm.assert_series_equal(result, expected)

            result = ser < "a"
            expected = Series([False, False, False, False, False])
            tm.assert_series_equal(result, expected)

            result = ser != "a"
            expected = -(ser == "a")
            tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("dtype", [None, object])
    def test_more_na_comparisons(self, dtype):
        left = Series(["a", np.nan, "c"], dtype=dtype)
        right = Series(["a", np.nan, "d"], dtype=dtype)

        result = left == right
        expected = Series([True, False, False])
        tm.assert_series_equal(result, expected)

        result = left != right
        expected = Series([False, True, True])
        tm.assert_series_equal(result, expected)

        result = left == np.nan
        expected = Series([False, False, False])
        tm.assert_series_equal(result, expected)

        result = left != np.nan
        expected = Series([True, True, True])
        tm.assert_series_equal(result, expected)


# ------------------------------------------------------------------
# Arithmetic


class TestArithmetic:
    def test_add_period_to_array_of_offset(self):
        # GH#50162
        per = pd.Period("2012-1-1", freq="D")
        pi = pd.period_range("2012-1-1", periods=10, freq="D")
        idx = per - pi

        expected = pd.Index([x + per for x in idx], dtype=object)
        result = idx + per
        tm.assert_index_equal(result, expected)

        result = per + idx
        tm.assert_index_equal(result, expected)

    # TODO: parametrize
    def test_pow_ops_object(self):
        # GH#22922
        # pow is weird with masking & 1, so testing here
        a = Series([1, np.nan, 1, np.nan], dtype=object)
        b = Series([1, np.nan, np.nan, 1], dtype=object)
        result = a**b
        expected = Series(a.values**b.values, dtype=object)
        tm.assert_series_equal(result, expected)

        result = b**a
        expected = Series(b.values**a.values, dtype=object)

        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("op", [operator.add, ops.radd])
    @pytest.mark.parametrize("other", ["category", "Int64"])
    def test_add_extension_scalar(self, other, box_with_array, op):
        # GH#22378
        # Check that scalars satisfying is_extension_array_dtype(obj)
        # do not incorrectly try to dispatch to an ExtensionArray operation

        arr = Series(["a", "b", "c"])
        expected = Series([op(x, other) for x in arr])

        arr = tm.box_expected(arr, box_with_array)
        expected = tm.box_expected(expected, box_with_array)

        result = op(arr, other)
        tm.assert_equal(result, expected)

    def test_objarr_add_str(self, box_with_array):
        ser = Series(["x", np.nan, "x"])
        expected = Series(["xa", np.nan, "xa"])

        ser = tm.box_expected(ser, box_with_array)
        expected = tm.box_expected(expected, box_with_array)

        result = ser + "a"
        tm.assert_equal(result, expected)

    def test_objarr_radd_str(self, box_with_array):
        ser = Series(["x", np.nan, "x"])
        expected = Series(["ax", np.nan, "ax"])

        ser = tm.box_expected(ser, box_with_array)
        expected = tm.box_expected(expected, box_with_array)

        result = "a" + ser
        tm.assert_equal(result, expected)

    @pytest.mark.parametrize(
        "data",
        [
            [1, 2, 3],
            [1.1, 2.2, 3.3],
            [Timestamp("2011-01-01"), Timestamp("2011-01-02"), pd.NaT],
            ["x", "y", 1],
        ],
    )
    @pytest.mark.parametrize("dtype", [None, object])
    def test_objarr_radd_str_invalid(self, dtype, data, box_with_array):
        ser = Series(data, dtype=dtype)

        ser = tm.box_expected(ser, box_with_array)
        msg = "|".join(
            [
                "can only concatenate str",
                "did not contain a loop with signature matching types",
                "unsupported operand type",
                "must be str",
            ]
        )
        with pytest.raises(TypeError, match=msg):
            "foo_" + ser

    @pytest.mark.parametrize("op", [operator.add, ops.radd, operator.sub, ops.rsub])
    def test_objarr_add_invalid(self, op, box_with_array):
        # invalid ops
        box = box_with_array

        obj_ser = Series(list("abc"), dtype=object, name="objects")

        obj_ser = tm.box_expected(obj_ser, box)
        msg = "|".join(
            [
                "can only concatenate str",
                "unsupported operand type",
                "must be str",
                "has no kernel",
                "operation 'add' not supported",
                "operation 'radd' not supported",
                "operation 'sub' not supported",
                "operation 'rsub' not supported",
            ]
        )
        with pytest.raises(Exception, match=msg):
            op(obj_ser, 1)
        with pytest.raises(Exception, match=msg):
            op(obj_ser, np.array(1, dtype=np.int64))

    # TODO: Moved from tests.series.test_operators; needs cleanup
    def test_operators_na_handling(self):
        ser = Series(["foo", "bar", "baz", np.nan])
        result = "prefix_" + ser
        expected = Series(["prefix_foo", "prefix_bar", "prefix_baz", np.nan])
        tm.assert_series_equal(result, expected)

        result = ser + "_suffix"
        expected = Series(["foo_suffix", "bar_suffix", "baz_suffix", np.nan])
        tm.assert_series_equal(result, expected)

    # TODO: parametrize over box
    @pytest.mark.parametrize("dtype", [None, object])
    def test_series_with_dtype_radd_timedelta(self, dtype):
        # note this test is _not_ aimed at timedelta64-dtyped Series
        # as of 2.0 we retain object dtype when ser.dtype == object
        ser = Series(
            [pd.Timedelta("1 days"), pd.Timedelta("2 days"), pd.Timedelta("3 days")],
            dtype=dtype,
        )
        expected = Series(
            [pd.Timedelta("4 days"), pd.Timedelta("5 days"), pd.Timedelta("6 days")],
            dtype=dtype,
        )

        result = pd.Timedelta("3 days") + ser
        tm.assert_series_equal(result, expected)

        result = ser + pd.Timedelta("3 days")
        tm.assert_series_equal(result, expected)

    # TODO: cleanup & parametrize over box
    def test_mixed_timezone_series_ops_object(self):
        # GH#13043
        ser = Series(
            [
                Timestamp("2015-01-01", tz="US/Eastern"),
                Timestamp("2015-01-01", tz="Asia/Tokyo"),
            ],
            name="xxx",
        )
        assert ser.dtype == object

        exp = Series(
            [
                Timestamp("2015-01-02", tz="US/Eastern"),
                Timestamp("2015-01-02", tz="Asia/Tokyo"),
            ],
            name="xxx",
        )
        tm.assert_series_equal(ser + pd.Timedelta("1 days"), exp)
        tm.assert_series_equal(pd.Timedelta("1 days") + ser, exp)

        # object series & object series
        ser2 = Series(
            [
                Timestamp("2015-01-03", tz="US/Eastern"),
                Timestamp("2015-01-05", tz="Asia/Tokyo"),
            ],
            name="xxx",
        )
        assert ser2.dtype == object
        exp = Series(
            [pd.Timedelta("2 days"), pd.Timedelta("4 days")], name="xxx", dtype=object
        )
        tm.assert_series_equal(ser2 - ser, exp)
        tm.assert_series_equal(ser - ser2, -exp)

        ser = Series(
            [pd.Timedelta("01:00:00"), pd.Timedelta("02:00:00")],
            name="xxx",
            dtype=object,
        )
        assert ser.dtype == object

        exp = Series(
            [pd.Timedelta("01:30:00"), pd.Timedelta("02:30:00")],
            name="xxx",
            dtype=object,
        )
        tm.assert_series_equal(ser + pd.Timedelta("00:30:00"), exp)
        tm.assert_series_equal(pd.Timedelta("00:30:00") + ser, exp)

    # TODO: cleanup & parametrize over box
    def test_iadd_preserves_name(self):
        # GH#17067, GH#19723 __iadd__ and __isub__ should preserve index name
        ser = Series([1, 2, 3])
        ser.index.name = "foo"

        ser.index += 1
        assert ser.index.name == "foo"

        ser.index -= 1
        assert ser.index.name == "foo"

    def test_add_string(self):
        # from bug report
        index = pd.Index(["a", "b", "c"])
        index2 = index + "foo"

        assert "a" not in index2
        assert "afoo" in index2

    def test_iadd_string(self):
        index = pd.Index(["a", "b", "c"])
        # doesn't fail test unless there is a check before `+=`
        assert "a" in index

        index += "_x"
        assert "a_x" in index

    def test_add(self):
        index = pd.Index([str(i) for i in range(10)])
        expected = pd.Index(index.values * 2)
        tm.assert_index_equal(index + index, expected)
        tm.assert_index_equal(index + index.tolist(), expected)
        tm.assert_index_equal(index.tolist() + index, expected)

        # test add and radd
        index = pd.Index(list("abc"))
        expected = pd.Index(["a1", "b1", "c1"])
        tm.assert_index_equal(index + "1", expected)
        expected = pd.Index(["1a", "1b", "1c"])
        tm.assert_index_equal("1" + index, expected)

    def test_sub_fail(self):
        index = pd.Index([str(i) for i in range(10)])

        msg = "unsupported operand type|Cannot broadcast|sub' not supported"
        with pytest.raises(TypeError, match=msg):
            index - "a"
        with pytest.raises(TypeError, match=msg):
            index - index
        with pytest.raises(TypeError, match=msg):
            index - index.tolist()
        with pytest.raises(TypeError, match=msg):
            index.tolist() - index

    def test_sub_object(self):
        # GH#19369
        index = pd.Index([Decimal(1), Decimal(2)])
        expected = pd.Index([Decimal(0), Decimal(1)])

        result = index - Decimal(1)
        tm.assert_index_equal(result, expected)

        result = index - pd.Index([Decimal(1), Decimal(1)])
        tm.assert_index_equal(result, expected)

        msg = "unsupported operand type"
        with pytest.raises(TypeError, match=msg):
            index - "foo"

        with pytest.raises(TypeError, match=msg):
            index - np.array([2, "foo"], dtype=object)

    def test_rsub_object(self, fixed_now_ts):
        # GH#19369
        index = pd.Index([Decimal(1), Decimal(2)])
        expected = pd.Index([Decimal(1), Decimal(0)])

        result = Decimal(2) - index
        tm.assert_index_equal(result, expected)

        result = np.array([Decimal(2), Decimal(2)]) - index
        tm.assert_index_equal(result, expected)

        msg = "unsupported operand type"
        with pytest.raises(TypeError, match=msg):
            "foo" - index

        with pytest.raises(TypeError, match=msg):
            np.array([True, fixed_now_ts]) - index


class MyIndex(pd.Index):
    # Simple index subclass that tracks ops calls.

    _calls: int

    @classmethod
    def _simple_new(cls, values, name=None, dtype=None):
        result = object.__new__(cls)
        result._data = values
        result._name = name
        result._calls = 0
        result._reset_identity()

        return result

    def __add__(self, other):
        self._calls += 1
        return self._simple_new(self._data)

    def __radd__(self, other):
        return self.__add__(other)


@pytest.mark.parametrize(
    "other",
    [
        [datetime.timedelta(1), datetime.timedelta(2)],
        [datetime.datetime(2000, 1, 1), datetime.datetime(2000, 1, 2)],
        [pd.Period("2000"), pd.Period("2001")],
        ["a", "b"],
    ],
    ids=["timedelta", "datetime", "period", "object"],
)
def test_index_ops_defer_to_unknown_subclasses(other):
    # https://github.com/pandas-dev/pandas/issues/31109
    values = np.array(
        [datetime.date(2000, 1, 1), datetime.date(2000, 1, 2)], dtype=object
    )
    a = MyIndex._simple_new(values)
    other = pd.Index(other)
    result = other + a
    assert isinstance(result, MyIndex)
    assert a._calls == 1
