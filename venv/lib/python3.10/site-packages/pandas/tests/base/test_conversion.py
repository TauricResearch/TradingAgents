import numpy as np
import pytest

from pandas.compat import HAS_PYARROW
from pandas.compat.numpy import np_version_gt2

from pandas.core.dtypes.dtypes import DatetimeTZDtype

import pandas as pd
from pandas import (
    CategoricalIndex,
    Series,
    Timedelta,
    Timestamp,
    date_range,
)
import pandas._testing as tm
from pandas.core.arrays import (
    DatetimeArray,
    IntervalArray,
    NumpyExtensionArray,
    PeriodArray,
    SparseArray,
    TimedeltaArray,
)
from pandas.core.arrays.string_ import StringArrayNumpySemantics
from pandas.core.arrays.string_arrow import ArrowStringArrayNumpySemantics


class TestToIterable:
    # test that we convert an iterable to python types

    dtypes = [
        ("int8", int),
        ("int16", int),
        ("int32", int),
        ("int64", int),
        ("uint8", int),
        ("uint16", int),
        ("uint32", int),
        ("uint64", int),
        ("float16", float),
        ("float32", float),
        ("float64", float),
        ("datetime64[ns]", Timestamp),
        ("datetime64[ns, US/Eastern]", Timestamp),
        ("timedelta64[ns]", Timedelta),
    ]

    @pytest.mark.parametrize("dtype, rdtype", dtypes)
    @pytest.mark.parametrize(
        "method",
        [
            lambda x: x.tolist(),
            lambda x: x.to_list(),
            lambda x: list(x),
            lambda x: list(x.__iter__()),
        ],
        ids=["tolist", "to_list", "list", "iter"],
    )
    def test_iterable(self, index_or_series, method, dtype, rdtype):
        # gh-10904
        # gh-13258
        # coerce iteration to underlying python / pandas types
        typ = index_or_series
        if dtype == "float16" and issubclass(typ, pd.Index):
            with pytest.raises(NotImplementedError, match="float16 indexes are not "):
                typ([1], dtype=dtype)
            return
        s = typ([1], dtype=dtype)
        result = method(s)[0]
        assert isinstance(result, rdtype)

    @pytest.mark.parametrize(
        "dtype, rdtype, obj",
        [
            ("object", object, "a"),
            ("object", int, 1),
            ("category", object, "a"),
            ("category", int, 1),
        ],
    )
    @pytest.mark.parametrize(
        "method",
        [
            lambda x: x.tolist(),
            lambda x: x.to_list(),
            lambda x: list(x),
            lambda x: list(x.__iter__()),
        ],
        ids=["tolist", "to_list", "list", "iter"],
    )
    def test_iterable_object_and_category(
        self, index_or_series, method, dtype, rdtype, obj
    ):
        # gh-10904
        # gh-13258
        # coerce iteration to underlying python / pandas types
        typ = index_or_series
        s = typ([obj], dtype=dtype)
        result = method(s)[0]
        assert isinstance(result, rdtype)

    @pytest.mark.parametrize("dtype, rdtype", dtypes)
    def test_iterable_items(self, dtype, rdtype):
        # gh-13258
        # test if items yields the correct boxed scalars
        # this only applies to series
        s = Series([1], dtype=dtype)
        _, result = next(iter(s.items()))
        assert isinstance(result, rdtype)

        _, result = next(iter(s.items()))
        assert isinstance(result, rdtype)

    @pytest.mark.parametrize(
        "dtype, rdtype", dtypes + [("object", int), ("category", int)]
    )
    def test_iterable_map(self, index_or_series, dtype, rdtype):
        # gh-13236
        # coerce iteration to underlying python / pandas types
        typ = index_or_series
        if dtype == "float16" and issubclass(typ, pd.Index):
            with pytest.raises(NotImplementedError, match="float16 indexes are not "):
                typ([1], dtype=dtype)
            return
        s = typ([1], dtype=dtype)
        result = s.map(type)[0]
        if not isinstance(rdtype, tuple):
            rdtype = (rdtype,)
        assert result in rdtype

    @pytest.mark.parametrize(
        "method",
        [
            lambda x: x.tolist(),
            lambda x: x.to_list(),
            lambda x: list(x),
            lambda x: list(x.__iter__()),
        ],
        ids=["tolist", "to_list", "list", "iter"],
    )
    def test_categorial_datetimelike(self, method):
        i = CategoricalIndex([Timestamp("1999-12-31"), Timestamp("2000-12-31")])

        result = method(i)[0]
        assert isinstance(result, Timestamp)

    def test_iter_box_dt64(self, unit):
        vals = [Timestamp("2011-01-01"), Timestamp("2011-01-02")]
        ser = Series(vals).dt.as_unit(unit)
        assert ser.dtype == f"datetime64[{unit}]"
        for res, exp in zip(ser, vals):
            assert isinstance(res, Timestamp)
            assert res.tz is None
            assert res == exp
            assert res.unit == unit

    def test_iter_box_dt64tz(self, unit):
        vals = [
            Timestamp("2011-01-01", tz="US/Eastern"),
            Timestamp("2011-01-02", tz="US/Eastern"),
        ]
        ser = Series(vals).dt.as_unit(unit)

        assert ser.dtype == f"datetime64[{unit}, US/Eastern]"
        for res, exp in zip(ser, vals):
            assert isinstance(res, Timestamp)
            assert res.tz == exp.tz
            assert res == exp
            assert res.unit == unit

    def test_iter_box_timedelta64(self, unit):
        # timedelta
        vals = [Timedelta("1 days"), Timedelta("2 days")]
        ser = Series(vals).dt.as_unit(unit)
        assert ser.dtype == f"timedelta64[{unit}]"
        for res, exp in zip(ser, vals):
            assert isinstance(res, Timedelta)
            assert res == exp
            assert res.unit == unit

    def test_iter_box_period(self):
        # period
        vals = [pd.Period("2011-01-01", freq="M"), pd.Period("2011-01-02", freq="M")]
        s = Series(vals)
        assert s.dtype == "Period[M]"
        for res, exp in zip(s, vals):
            assert isinstance(res, pd.Period)
            assert res.freq == "ME"
            assert res == exp


@pytest.mark.parametrize(
    "arr, expected_type, dtype",
    [
        (np.array([0, 1], dtype=np.int64), np.ndarray, "int64"),
        (np.array(["a", "b"]), np.ndarray, "object"),
        (pd.Categorical(["a", "b"]), pd.Categorical, "category"),
        (
            pd.DatetimeIndex(["2017", "2018"], tz="US/Central"),
            DatetimeArray,
            "datetime64[ns, US/Central]",
        ),
        (
            pd.PeriodIndex([2018, 2019], freq="Y"),
            PeriodArray,
            pd.core.dtypes.dtypes.PeriodDtype("Y-DEC"),
        ),
        (pd.IntervalIndex.from_breaks([0, 1, 2]), IntervalArray, "interval"),
        (
            pd.DatetimeIndex(["2017", "2018"]),
            DatetimeArray,
            "datetime64[ns]",
        ),
        (
            pd.TimedeltaIndex([10**10]),
            TimedeltaArray,
            "m8[ns]",
        ),
    ],
)
def test_values_consistent(arr, expected_type, dtype, using_infer_string):
    if using_infer_string and dtype == "object":
        expected_type = (
            ArrowStringArrayNumpySemantics if HAS_PYARROW else StringArrayNumpySemantics
        )
    l_values = Series(arr)._values
    r_values = pd.Index(arr)._values
    assert type(l_values) is expected_type
    assert type(l_values) is type(r_values)

    tm.assert_equal(l_values, r_values)


@pytest.mark.parametrize("arr", [np.array([1, 2, 3])])
def test_numpy_array(arr):
    ser = Series(arr)
    result = ser.array
    expected = NumpyExtensionArray(arr)
    tm.assert_extension_array_equal(result, expected)


def test_numpy_array_all_dtypes(any_numpy_dtype):
    ser = Series(dtype=any_numpy_dtype)
    result = ser.array
    if np.dtype(any_numpy_dtype).kind == "M":
        assert isinstance(result, DatetimeArray)
    elif np.dtype(any_numpy_dtype).kind == "m":
        assert isinstance(result, TimedeltaArray)
    else:
        assert isinstance(result, NumpyExtensionArray)


@pytest.mark.parametrize(
    "arr, attr",
    [
        (pd.Categorical(["a", "b"]), "_codes"),
        (PeriodArray._from_sequence(["2000", "2001"], dtype="period[D]"), "_ndarray"),
        (pd.array([0, np.nan], dtype="Int64"), "_data"),
        (IntervalArray.from_breaks([0, 1]), "_left"),
        (SparseArray([0, 1]), "_sparse_values"),
        (
            DatetimeArray._from_sequence(np.array([1, 2], dtype="datetime64[ns]")),
            "_ndarray",
        ),
        # tz-aware Datetime
        (
            DatetimeArray._from_sequence(
                np.array(
                    ["2000-01-01T12:00:00", "2000-01-02T12:00:00"], dtype="M8[ns]"
                ),
                dtype=DatetimeTZDtype(tz="US/Central"),
            ),
            "_ndarray",
        ),
    ],
)
def test_array(arr, attr, index_or_series, request):
    box = index_or_series

    result = box(arr, copy=False).array

    if attr:
        arr = getattr(arr, attr)
        result = getattr(result, attr)

    assert result is arr


def test_array_multiindex_raises():
    idx = pd.MultiIndex.from_product([["A"], ["a", "b"]])
    msg = "MultiIndex has no single backing array"
    with pytest.raises(ValueError, match=msg):
        idx.array


@pytest.mark.parametrize(
    "arr, expected, zero_copy",
    [
        (np.array([1, 2], dtype=np.int64), np.array([1, 2], dtype=np.int64), True),
        (pd.Categorical(["a", "b"]), np.array(["a", "b"], dtype=object), False),
        (
            pd.core.arrays.period_array(["2000", "2001"], freq="D"),
            np.array([pd.Period("2000", freq="D"), pd.Period("2001", freq="D")]),
            False,
        ),
        (pd.array([0, np.nan], dtype="Int64"), np.array([0, np.nan]), False),
        (
            IntervalArray.from_breaks([0, 1, 2]),
            np.array([pd.Interval(0, 1), pd.Interval(1, 2)], dtype=object),
            False,
        ),
        (SparseArray([0, 1]), np.array([0, 1], dtype=np.int64), False),
        # tz-naive datetime
        (
            DatetimeArray._from_sequence(np.array(["2000", "2001"], dtype="M8[ns]")),
            np.array(["2000", "2001"], dtype="M8[ns]"),
            True,
        ),
        # tz-aware stays tz`-aware
        (
            DatetimeArray._from_sequence(
                np.array(["2000-01-01T06:00:00", "2000-01-02T06:00:00"], dtype="M8[ns]")
            )
            .tz_localize("UTC")
            .tz_convert("US/Central"),
            np.array(
                [
                    Timestamp("2000-01-01", tz="US/Central"),
                    Timestamp("2000-01-02", tz="US/Central"),
                ]
            ),
            False,
        ),
        # Timedelta
        (
            TimedeltaArray._from_sequence(
                np.array([0, 3600000000000], dtype="i8").view("m8[ns]")
            ),
            np.array([0, 3600000000000], dtype="m8[ns]"),
            True,
        ),
        # GH#26406 tz is preserved in Categorical[dt64tz]
        (
            pd.Categorical(date_range("2016-01-01", periods=2, tz="US/Pacific")),
            np.array(
                [
                    Timestamp("2016-01-01", tz="US/Pacific"),
                    Timestamp("2016-01-02", tz="US/Pacific"),
                ]
            ),
            False,
        ),
    ],
)
def test_to_numpy(arr, expected, zero_copy, index_or_series_or_array):
    box = index_or_series_or_array

    with tm.assert_produces_warning(None):
        thing = box(arr)

    result = thing.to_numpy()
    tm.assert_numpy_array_equal(result, expected)

    result = np.asarray(thing)
    tm.assert_numpy_array_equal(result, expected)

    # Additionally, we check the `copy=` semantics for array/asarray
    # (these are implemented by us via `__array__`).
    result_cp1 = np.array(thing, copy=True)
    result_cp2 = np.array(thing, copy=True)
    # When called with `copy=True` NumPy/we should ensure a copy was made
    assert not np.may_share_memory(result_cp1, result_cp2)

    if not np_version_gt2:
        # copy=False semantics are only supported in NumPy>=2.
        return

    if not zero_copy:
        msg = "Starting with NumPy 2.0, the behavior of the 'copy' keyword has changed"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            np.array(thing, copy=False)

    else:
        result_nocopy1 = np.array(thing, copy=False)
        result_nocopy2 = np.array(thing, copy=False)
        # If copy=False was given, these must share the same data
        assert np.may_share_memory(result_nocopy1, result_nocopy2)


@pytest.mark.parametrize("as_series", [True, False])
@pytest.mark.parametrize(
    "arr", [np.array([1, 2, 3], dtype="int64"), np.array(["a", "b", "c"], dtype=object)]
)
def test_to_numpy_copy(arr, as_series, using_infer_string):
    obj = pd.Index(arr, copy=False)
    if as_series:
        obj = Series(obj.values, copy=False)

    # no copy by default
    result = obj.to_numpy()
    if using_infer_string and arr.dtype == object and obj.dtype.storage == "pyarrow":
        assert np.shares_memory(arr, result) is False
    else:
        assert np.shares_memory(arr, result) is True

    result = obj.to_numpy(copy=False)
    if using_infer_string and arr.dtype == object and obj.dtype.storage == "pyarrow":
        assert np.shares_memory(arr, result) is False
    else:
        assert np.shares_memory(arr, result) is True

    # copy=True
    result = obj.to_numpy(copy=True)
    assert np.shares_memory(arr, result) is False


@pytest.mark.parametrize("as_series", [True, False])
def test_to_numpy_dtype(as_series, unit):
    tz = "US/Eastern"
    obj = pd.DatetimeIndex(["2000", "2001"], tz=tz)
    if as_series:
        obj = Series(obj)

    # preserve tz by default
    result = obj.to_numpy()
    expected = np.array(
        [Timestamp("2000", tz=tz), Timestamp("2001", tz=tz)], dtype=object
    )
    tm.assert_numpy_array_equal(result, expected)

    result = obj.to_numpy(dtype="object")
    tm.assert_numpy_array_equal(result, expected)

    result = obj.to_numpy(dtype="M8[ns]")
    expected = np.array(["2000-01-01T05", "2001-01-01T05"], dtype="M8[ns]")
    tm.assert_numpy_array_equal(result, expected)


@pytest.mark.parametrize(
    "values, dtype, na_value, expected",
    [
        ([1, 2, None], "float64", 0, [1.0, 2.0, 0.0]),
        (
            [Timestamp("2000"), Timestamp("2000"), pd.NaT],
            None,
            Timestamp("2000"),
            [np.datetime64("2000-01-01T00:00:00.000000000")] * 3,
        ),
    ],
)
def test_to_numpy_na_value_numpy_dtype(
    index_or_series, values, dtype, na_value, expected
):
    obj = index_or_series(values)
    result = obj.to_numpy(dtype=dtype, na_value=na_value)
    expected = np.array(expected)
    tm.assert_numpy_array_equal(result, expected)


@pytest.mark.parametrize(
    "data, multiindex, dtype, na_value, expected",
    [
        (
            [1, 2, None, 4],
            [(0, "a"), (0, "b"), (1, "b"), (1, "c")],
            float,
            None,
            [1.0, 2.0, np.nan, 4.0],
        ),
        (
            [1, 2, None, 4],
            [(0, "a"), (0, "b"), (1, "b"), (1, "c")],
            float,
            np.nan,
            [1.0, 2.0, np.nan, 4.0],
        ),
        (
            [1.0, 2.0, np.nan, 4.0],
            [("a", 0), ("a", 1), ("a", 2), ("b", 0)],
            int,
            0,
            [1, 2, 0, 4],
        ),
        (
            [Timestamp("2000"), Timestamp("2000"), pd.NaT],
            [(0, Timestamp("2021")), (0, Timestamp("2022")), (1, Timestamp("2000"))],
            None,
            Timestamp("2000"),
            [np.datetime64("2000-01-01T00:00:00.000000000")] * 3,
        ),
    ],
)
def test_to_numpy_multiindex_series_na_value(
    data, multiindex, dtype, na_value, expected
):
    index = pd.MultiIndex.from_tuples(multiindex)
    series = Series(data, index=index)
    result = series.to_numpy(dtype=dtype, na_value=na_value)
    expected = np.array(expected)
    tm.assert_numpy_array_equal(result, expected)


def test_to_numpy_kwargs_raises():
    # numpy
    s = Series([1, 2, 3])
    msg = r"to_numpy\(\) got an unexpected keyword argument 'foo'"
    with pytest.raises(TypeError, match=msg):
        s.to_numpy(foo=True)

    # extension
    s = Series([1, 2, 3], dtype="Int64")
    with pytest.raises(TypeError, match=msg):
        s.to_numpy(foo=True)


@pytest.mark.parametrize(
    "data",
    [
        {"a": [1, 2, 3], "b": [1, 2, None]},
        {"a": np.array([1, 2, 3]), "b": np.array([1, 2, np.nan])},
        {"a": pd.array([1, 2, 3]), "b": pd.array([1, 2, None])},
    ],
)
@pytest.mark.parametrize("dtype, na_value", [(float, np.nan), (object, None)])
def test_to_numpy_dataframe_na_value(data, dtype, na_value):
    # https://github.com/pandas-dev/pandas/issues/33820
    df = pd.DataFrame(data)
    result = df.to_numpy(dtype=dtype, na_value=na_value)
    expected = np.array([[1, 1], [2, 2], [3, na_value]], dtype=dtype)
    tm.assert_numpy_array_equal(result, expected)


@pytest.mark.parametrize(
    "data, expected",
    [
        (
            {"a": pd.array([1, 2, None])},
            np.array([[1.0], [2.0], [np.nan]], dtype=float),
        ),
        (
            {"a": [1, 2, 3], "b": [1, 2, 3]},
            np.array([[1, 1], [2, 2], [3, 3]], dtype=float),
        ),
    ],
)
def test_to_numpy_dataframe_single_block(data, expected):
    # https://github.com/pandas-dev/pandas/issues/33820
    df = pd.DataFrame(data)
    result = df.to_numpy(dtype=float, na_value=np.nan)
    tm.assert_numpy_array_equal(result, expected)


def test_to_numpy_dataframe_single_block_no_mutate():
    # https://github.com/pandas-dev/pandas/issues/33820
    result = pd.DataFrame(np.array([1.0, 2.0, np.nan]))
    expected = pd.DataFrame(np.array([1.0, 2.0, np.nan]))
    result.to_numpy(na_value=0.0)
    tm.assert_frame_equal(result, expected)


class TestAsArray:
    @pytest.mark.parametrize("tz", [None, "US/Central"])
    def test_asarray_object_dt64(self, tz):
        ser = Series(date_range("2000", periods=2, tz=tz))

        with tm.assert_produces_warning(None):
            # Future behavior (for tzaware case) with no warning
            result = np.asarray(ser, dtype=object)

        expected = np.array(
            [Timestamp("2000-01-01", tz=tz), Timestamp("2000-01-02", tz=tz)]
        )
        tm.assert_numpy_array_equal(result, expected)

    def test_asarray_tz_naive(self):
        # This shouldn't produce a warning.
        ser = Series(date_range("2000", periods=2))
        expected = np.array(["2000-01-01", "2000-01-02"], dtype="M8[ns]")
        result = np.asarray(ser)

        tm.assert_numpy_array_equal(result, expected)

    def test_asarray_tz_aware(self):
        tz = "US/Central"
        ser = Series(date_range("2000", periods=2, tz=tz))
        expected = np.array(["2000-01-01T06", "2000-01-02T06"], dtype="M8[ns]")
        result = np.asarray(ser, dtype="datetime64[ns]")

        tm.assert_numpy_array_equal(result, expected)

        # Old behavior with no warning
        result = np.asarray(ser, dtype="M8[ns]")

        tm.assert_numpy_array_equal(result, expected)
