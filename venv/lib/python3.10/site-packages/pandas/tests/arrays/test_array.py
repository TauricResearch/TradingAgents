import datetime
import decimal
import re

import numpy as np
import pytest
import pytz

from pandas._config import using_string_dtype

import pandas as pd
import pandas._testing as tm
from pandas.api.extensions import register_extension_dtype
from pandas.arrays import (
    BooleanArray,
    DatetimeArray,
    FloatingArray,
    IntegerArray,
    IntervalArray,
    SparseArray,
    TimedeltaArray,
)
from pandas.core.arrays import (
    NumpyExtensionArray,
    period_array,
)
from pandas.tests.extension.decimal import (
    DecimalArray,
    DecimalDtype,
    to_decimal,
)


@pytest.mark.parametrize("dtype_unit", ["M8[h]", "M8[m]", "m8[h]", "M8[m]"])
def test_dt64_array(dtype_unit):
    # PR 53817
    dtype_var = np.dtype(dtype_unit)
    msg = (
        r"datetime64 and timedelta64 dtype resolutions other than "
        r"'s', 'ms', 'us', and 'ns' are deprecated. "
        r"In future releases passing unsupported resolutions will "
        r"raise an exception."
    )
    with tm.assert_produces_warning(FutureWarning, match=re.escape(msg)):
        pd.array([], dtype=dtype_var)


@pytest.mark.parametrize(
    "data, dtype, expected",
    [
        # Basic NumPy defaults.
        ([], None, FloatingArray._from_sequence([], dtype="Float64")),
        ([1, 2], None, IntegerArray._from_sequence([1, 2], dtype="Int64")),
        ([1, 2], object, NumpyExtensionArray(np.array([1, 2], dtype=object))),
        (
            [1, 2],
            np.dtype("float32"),
            NumpyExtensionArray(np.array([1.0, 2.0], dtype=np.dtype("float32"))),
        ),
        (
            np.array([], dtype=object),
            None,
            NumpyExtensionArray(np.array([], dtype=object)),
        ),
        (
            np.array([1, 2], dtype="int64"),
            None,
            IntegerArray._from_sequence([1, 2], dtype="Int64"),
        ),
        (
            np.array([1.0, 2.0], dtype="float64"),
            None,
            FloatingArray._from_sequence([1.0, 2.0], dtype="Float64"),
        ),
        # String alias passes through to NumPy
        ([1, 2], "float32", NumpyExtensionArray(np.array([1, 2], dtype="float32"))),
        ([1, 2], "int64", NumpyExtensionArray(np.array([1, 2], dtype=np.int64))),
        # GH#44715 FloatingArray does not support float16, so fall
        #  back to NumpyExtensionArray
        (
            np.array([1, 2], dtype=np.float16),
            None,
            NumpyExtensionArray(np.array([1, 2], dtype=np.float16)),
        ),
        # idempotency with e.g. pd.array(pd.array([1, 2], dtype="int64"))
        (
            NumpyExtensionArray(np.array([1, 2], dtype=np.int32)),
            None,
            NumpyExtensionArray(np.array([1, 2], dtype=np.int32)),
        ),
        # Period alias
        (
            [pd.Period("2000", "D"), pd.Period("2001", "D")],
            "Period[D]",
            period_array(["2000", "2001"], freq="D"),
        ),
        # Period dtype
        (
            [pd.Period("2000", "D")],
            pd.PeriodDtype("D"),
            period_array(["2000"], freq="D"),
        ),
        # Datetime (naive)
        (
            [1, 2],
            np.dtype("datetime64[ns]"),
            DatetimeArray._from_sequence(
                np.array([1, 2], dtype="M8[ns]"), dtype="M8[ns]"
            ),
        ),
        (
            [1, 2],
            np.dtype("datetime64[s]"),
            DatetimeArray._from_sequence(
                np.array([1, 2], dtype="M8[s]"), dtype="M8[s]"
            ),
        ),
        (
            np.array([1, 2], dtype="datetime64[ns]"),
            None,
            DatetimeArray._from_sequence(
                np.array([1, 2], dtype="M8[ns]"), dtype="M8[ns]"
            ),
        ),
        (
            pd.DatetimeIndex(["2000", "2001"]),
            np.dtype("datetime64[ns]"),
            DatetimeArray._from_sequence(["2000", "2001"], dtype="M8[ns]"),
        ),
        (
            pd.DatetimeIndex(["2000", "2001"]),
            None,
            DatetimeArray._from_sequence(["2000", "2001"], dtype="M8[ns]"),
        ),
        (
            ["2000", "2001"],
            np.dtype("datetime64[ns]"),
            DatetimeArray._from_sequence(["2000", "2001"], dtype="M8[ns]"),
        ),
        # Datetime (tz-aware)
        (
            ["2000", "2001"],
            pd.DatetimeTZDtype(tz="CET"),
            DatetimeArray._from_sequence(
                ["2000", "2001"], dtype=pd.DatetimeTZDtype(tz="CET")
            ),
        ),
        # Timedelta
        (
            ["1h", "2h"],
            np.dtype("timedelta64[ns]"),
            TimedeltaArray._from_sequence(["1h", "2h"], dtype="m8[ns]"),
        ),
        (
            pd.TimedeltaIndex(["1h", "2h"]),
            np.dtype("timedelta64[ns]"),
            TimedeltaArray._from_sequence(["1h", "2h"], dtype="m8[ns]"),
        ),
        (
            np.array([1, 2], dtype="m8[s]"),
            np.dtype("timedelta64[s]"),
            TimedeltaArray._from_sequence(
                np.array([1, 2], dtype="m8[s]"), dtype="m8[s]"
            ),
        ),
        (
            pd.TimedeltaIndex(["1h", "2h"]),
            None,
            TimedeltaArray._from_sequence(["1h", "2h"], dtype="m8[ns]"),
        ),
        (
            # preserve non-nano, i.e. don't cast to NumpyExtensionArray
            TimedeltaArray._simple_new(
                np.arange(5, dtype=np.int64).view("m8[s]"), dtype=np.dtype("m8[s]")
            ),
            None,
            TimedeltaArray._simple_new(
                np.arange(5, dtype=np.int64).view("m8[s]"), dtype=np.dtype("m8[s]")
            ),
        ),
        (
            # preserve non-nano, i.e. don't cast to NumpyExtensionArray
            TimedeltaArray._simple_new(
                np.arange(5, dtype=np.int64).view("m8[s]"), dtype=np.dtype("m8[s]")
            ),
            np.dtype("m8[s]"),
            TimedeltaArray._simple_new(
                np.arange(5, dtype=np.int64).view("m8[s]"), dtype=np.dtype("m8[s]")
            ),
        ),
        # Category
        (["a", "b"], "category", pd.Categorical(["a", "b"])),
        (
            ["a", "b"],
            pd.CategoricalDtype(None, ordered=True),
            pd.Categorical(["a", "b"], ordered=True),
        ),
        # Interval
        (
            [pd.Interval(1, 2), pd.Interval(3, 4)],
            "interval",
            IntervalArray.from_tuples([(1, 2), (3, 4)]),
        ),
        # Sparse
        ([0, 1], "Sparse[int64]", SparseArray([0, 1], dtype="int64")),
        # IntegerNA
        ([1, None], "Int16", pd.array([1, None], dtype="Int16")),
        (
            pd.Series([1, 2]),
            None,
            NumpyExtensionArray(np.array([1, 2], dtype=np.int64)),
        ),
        # String
        (
            ["a", None],
            "string",
            pd.StringDtype()
            .construct_array_type()
            ._from_sequence(["a", None], dtype=pd.StringDtype()),
        ),
        (
            ["a", None],
            "str",
            pd.StringDtype(na_value=np.nan)
            .construct_array_type()
            ._from_sequence(["a", None], dtype=pd.StringDtype(na_value=np.nan))
            if using_string_dtype()
            else NumpyExtensionArray(np.array(["a", "None"])),
        ),
        (
            ["a", None],
            pd.StringDtype(),
            pd.StringDtype()
            .construct_array_type()
            ._from_sequence(["a", None], dtype=pd.StringDtype()),
        ),
        (
            ["a", None],
            pd.StringDtype(na_value=np.nan),
            pd.StringDtype(na_value=np.nan)
            .construct_array_type()
            ._from_sequence(["a", None], dtype=pd.StringDtype(na_value=np.nan)),
        ),
        (
            # numpy array with string dtype
            np.array(["a", "b"], dtype=str),
            pd.StringDtype(),
            pd.StringDtype()
            .construct_array_type()
            ._from_sequence(["a", "b"], dtype=pd.StringDtype()),
        ),
        (
            # numpy array with string dtype
            np.array(["a", "b"], dtype=str),
            pd.StringDtype(na_value=np.nan),
            pd.StringDtype(na_value=np.nan)
            .construct_array_type()
            ._from_sequence(["a", "b"], dtype=pd.StringDtype(na_value=np.nan)),
        ),
        # Boolean
        (
            [True, None],
            "boolean",
            BooleanArray._from_sequence([True, None], dtype="boolean"),
        ),
        (
            [True, None],
            pd.BooleanDtype(),
            BooleanArray._from_sequence([True, None], dtype="boolean"),
        ),
        # Index
        (pd.Index([1, 2]), None, NumpyExtensionArray(np.array([1, 2], dtype=np.int64))),
        # Series[EA] returns the EA
        (
            pd.Series(pd.Categorical(["a", "b"], categories=["a", "b", "c"])),
            None,
            pd.Categorical(["a", "b"], categories=["a", "b", "c"]),
        ),
        # "3rd party" EAs work
        ([decimal.Decimal(0), decimal.Decimal(1)], "decimal", to_decimal([0, 1])),
        # pass an ExtensionArray, but a different dtype
        (
            period_array(["2000", "2001"], freq="D"),
            "category",
            pd.Categorical([pd.Period("2000", "D"), pd.Period("2001", "D")]),
        ),
    ],
)
def test_array(data, dtype, expected):
    result = pd.array(data, dtype=dtype)
    tm.assert_equal(result, expected)


def test_array_copy():
    a = np.array([1, 2])
    # default is to copy
    b = pd.array(a, dtype=a.dtype)
    assert not tm.shares_memory(a, b)

    # copy=True
    b = pd.array(a, dtype=a.dtype, copy=True)
    assert not tm.shares_memory(a, b)

    # copy=False
    b = pd.array(a, dtype=a.dtype, copy=False)
    assert tm.shares_memory(a, b)


cet = pytz.timezone("CET")


@pytest.mark.parametrize(
    "data, expected",
    [
        # period
        (
            [pd.Period("2000", "D"), pd.Period("2001", "D")],
            period_array(["2000", "2001"], freq="D"),
        ),
        # interval
        ([pd.Interval(0, 1), pd.Interval(1, 2)], IntervalArray.from_breaks([0, 1, 2])),
        # datetime
        (
            [pd.Timestamp("2000"), pd.Timestamp("2001")],
            DatetimeArray._from_sequence(["2000", "2001"], dtype="M8[ns]"),
        ),
        (
            [datetime.datetime(2000, 1, 1), datetime.datetime(2001, 1, 1)],
            DatetimeArray._from_sequence(["2000", "2001"], dtype="M8[ns]"),
        ),
        (
            np.array([1, 2], dtype="M8[ns]"),
            DatetimeArray._from_sequence(np.array([1, 2], dtype="M8[ns]")),
        ),
        (
            np.array([1, 2], dtype="M8[us]"),
            DatetimeArray._simple_new(
                np.array([1, 2], dtype="M8[us]"), dtype=np.dtype("M8[us]")
            ),
        ),
        # datetimetz
        (
            [pd.Timestamp("2000", tz="CET"), pd.Timestamp("2001", tz="CET")],
            DatetimeArray._from_sequence(
                ["2000", "2001"], dtype=pd.DatetimeTZDtype(tz="CET", unit="ns")
            ),
        ),
        (
            [
                datetime.datetime(2000, 1, 1, tzinfo=cet),
                datetime.datetime(2001, 1, 1, tzinfo=cet),
            ],
            DatetimeArray._from_sequence(
                ["2000", "2001"], dtype=pd.DatetimeTZDtype(tz=cet, unit="ns")
            ),
        ),
        # timedelta
        (
            [pd.Timedelta("1h"), pd.Timedelta("2h")],
            TimedeltaArray._from_sequence(["1h", "2h"], dtype="m8[ns]"),
        ),
        (
            np.array([1, 2], dtype="m8[ns]"),
            TimedeltaArray._from_sequence(np.array([1, 2], dtype="m8[ns]")),
        ),
        (
            np.array([1, 2], dtype="m8[us]"),
            TimedeltaArray._from_sequence(np.array([1, 2], dtype="m8[us]")),
        ),
        # integer
        ([1, 2], IntegerArray._from_sequence([1, 2], dtype="Int64")),
        ([1, None], IntegerArray._from_sequence([1, None], dtype="Int64")),
        ([1, pd.NA], IntegerArray._from_sequence([1, pd.NA], dtype="Int64")),
        ([1, np.nan], IntegerArray._from_sequence([1, np.nan], dtype="Int64")),
        # float
        ([0.1, 0.2], FloatingArray._from_sequence([0.1, 0.2], dtype="Float64")),
        ([0.1, None], FloatingArray._from_sequence([0.1, pd.NA], dtype="Float64")),
        ([0.1, np.nan], FloatingArray._from_sequence([0.1, pd.NA], dtype="Float64")),
        ([0.1, pd.NA], FloatingArray._from_sequence([0.1, pd.NA], dtype="Float64")),
        # integer-like float
        ([1.0, 2.0], FloatingArray._from_sequence([1.0, 2.0], dtype="Float64")),
        ([1.0, None], FloatingArray._from_sequence([1.0, pd.NA], dtype="Float64")),
        ([1.0, np.nan], FloatingArray._from_sequence([1.0, pd.NA], dtype="Float64")),
        ([1.0, pd.NA], FloatingArray._from_sequence([1.0, pd.NA], dtype="Float64")),
        # mixed-integer-float
        ([1, 2.0], FloatingArray._from_sequence([1.0, 2.0], dtype="Float64")),
        (
            [1, np.nan, 2.0],
            FloatingArray._from_sequence([1.0, None, 2.0], dtype="Float64"),
        ),
        # string
        (
            ["a", "b"],
            pd.StringDtype()
            .construct_array_type()
            ._from_sequence(["a", "b"], dtype=pd.StringDtype()),
        ),
        (
            ["a", None],
            pd.StringDtype()
            .construct_array_type()
            ._from_sequence(["a", None], dtype=pd.StringDtype()),
        ),
        (
            # numpy array with string dtype
            np.array(["a", "b"], dtype=str),
            pd.StringDtype()
            .construct_array_type()
            ._from_sequence(["a", "b"], dtype=pd.StringDtype()),
        ),
        # Boolean
        ([True, False], BooleanArray._from_sequence([True, False], dtype="boolean")),
        ([True, None], BooleanArray._from_sequence([True, None], dtype="boolean")),
    ],
)
def test_array_inference(data, expected):
    result = pd.array(data)
    tm.assert_equal(result, expected)


@pytest.mark.parametrize(
    "data",
    [
        # mix of frequencies
        [pd.Period("2000", "D"), pd.Period("2001", "Y")],
        # mix of closed
        [pd.Interval(0, 1, closed="left"), pd.Interval(1, 2, closed="right")],
        # Mix of timezones
        [pd.Timestamp("2000", tz="CET"), pd.Timestamp("2000", tz="UTC")],
        # Mix of tz-aware and tz-naive
        [pd.Timestamp("2000", tz="CET"), pd.Timestamp("2000")],
        np.array([pd.Timestamp("2000"), pd.Timestamp("2000", tz="CET")]),
    ],
)
def test_array_inference_fails(data):
    result = pd.array(data)
    expected = NumpyExtensionArray(np.array(data, dtype=object))
    tm.assert_extension_array_equal(result, expected)


@pytest.mark.parametrize("data", [np.array(0)])
def test_nd_raises(data):
    with pytest.raises(ValueError, match="NumpyExtensionArray must be 1-dimensional"):
        pd.array(data, dtype="int64")


def test_scalar_raises():
    with pytest.raises(ValueError, match="Cannot pass scalar '1'"):
        pd.array(1)


def test_dataframe_raises():
    # GH#51167 don't accidentally cast to StringArray by doing inference on columns
    df = pd.DataFrame([[1, 2], [3, 4]], columns=["A", "B"])
    msg = "Cannot pass DataFrame to 'pandas.array'"
    with pytest.raises(TypeError, match=msg):
        pd.array(df)


def test_bounds_check():
    # GH21796
    with pytest.raises(
        TypeError, match=r"cannot safely cast non-equivalent int(32|64) to uint16"
    ):
        pd.array([-1, 2, 3], dtype="UInt16")


# ---------------------------------------------------------------------------
# A couple dummy classes to ensure that Series and Indexes are unboxed before
# getting to the EA classes.


@register_extension_dtype
class DecimalDtype2(DecimalDtype):
    name = "decimal2"

    @classmethod
    def construct_array_type(cls):
        """
        Return the array type associated with this dtype.

        Returns
        -------
        type
        """
        return DecimalArray2


class DecimalArray2(DecimalArray):
    @classmethod
    def _from_sequence(cls, scalars, *, dtype=None, copy=False):
        if isinstance(scalars, (pd.Series, pd.Index)):
            raise TypeError("scalars should not be of type pd.Series or pd.Index")

        return super()._from_sequence(scalars, dtype=dtype, copy=copy)


def test_array_unboxes(index_or_series):
    box = index_or_series

    data = box([decimal.Decimal("1"), decimal.Decimal("2")])
    dtype = DecimalDtype2()
    # make sure it works
    with pytest.raises(
        TypeError, match="scalars should not be of type pd.Series or pd.Index"
    ):
        DecimalArray2._from_sequence(data, dtype=dtype)

    result = pd.array(data, dtype="decimal2")
    expected = DecimalArray2._from_sequence(data.values, dtype=dtype)
    tm.assert_equal(result, expected)


def test_array_to_numpy_na():
    # GH#40638
    arr = pd.array([pd.NA, 1], dtype="string[python]")
    result = arr.to_numpy(na_value=True, dtype=bool)
    expected = np.array([True, True])
    tm.assert_numpy_array_equal(result, expected)
