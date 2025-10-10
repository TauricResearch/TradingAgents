import numpy as np
import pytest

from pandas.core.dtypes.cast import find_common_type
from pandas.core.dtypes.common import pandas_dtype
from pandas.core.dtypes.dtypes import (
    CategoricalDtype,
    DatetimeTZDtype,
    IntervalDtype,
    PeriodDtype,
)

from pandas import (
    Categorical,
    Index,
)


@pytest.mark.parametrize(
    "source_dtypes,expected_common_dtype",
    [
        ((np.int64,), np.int64),
        ((np.uint64,), np.uint64),
        ((np.float32,), np.float32),
        ((object,), object),
        # Into ints.
        ((np.int16, np.int64), np.int64),
        ((np.int32, np.uint32), np.int64),
        ((np.uint16, np.uint64), np.uint64),
        # Into floats.
        ((np.float16, np.float32), np.float32),
        ((np.float16, np.int16), np.float32),
        ((np.float32, np.int16), np.float32),
        ((np.uint64, np.int64), np.float64),
        ((np.int16, np.float64), np.float64),
        ((np.float16, np.int64), np.float64),
        # Into others.
        ((np.complex128, np.int32), np.complex128),
        ((object, np.float32), object),
        ((object, np.int16), object),
        # Bool with int.
        ((np.dtype("bool"), np.int64), object),
        ((np.dtype("bool"), np.int32), object),
        ((np.dtype("bool"), np.int16), object),
        ((np.dtype("bool"), np.int8), object),
        ((np.dtype("bool"), np.uint64), object),
        ((np.dtype("bool"), np.uint32), object),
        ((np.dtype("bool"), np.uint16), object),
        ((np.dtype("bool"), np.uint8), object),
        # Bool with float.
        ((np.dtype("bool"), np.float64), object),
        ((np.dtype("bool"), np.float32), object),
        (
            (np.dtype("datetime64[ns]"), np.dtype("datetime64[ns]")),
            np.dtype("datetime64[ns]"),
        ),
        (
            (np.dtype("timedelta64[ns]"), np.dtype("timedelta64[ns]")),
            np.dtype("timedelta64[ns]"),
        ),
        (
            (np.dtype("datetime64[ns]"), np.dtype("datetime64[ms]")),
            np.dtype("datetime64[ns]"),
        ),
        (
            (np.dtype("timedelta64[ms]"), np.dtype("timedelta64[ns]")),
            np.dtype("timedelta64[ns]"),
        ),
        ((np.dtype("datetime64[ns]"), np.dtype("timedelta64[ns]")), object),
        ((np.dtype("datetime64[ns]"), np.int64), object),
    ],
)
def test_numpy_dtypes(source_dtypes, expected_common_dtype):
    source_dtypes = [pandas_dtype(x) for x in source_dtypes]
    assert find_common_type(source_dtypes) == expected_common_dtype


def test_raises_empty_input():
    with pytest.raises(ValueError, match="no types given"):
        find_common_type([])


@pytest.mark.parametrize(
    "dtypes,exp_type",
    [
        ([CategoricalDtype()], "category"),
        ([object, CategoricalDtype()], object),
        ([CategoricalDtype(), CategoricalDtype()], "category"),
    ],
)
def test_categorical_dtype(dtypes, exp_type):
    assert find_common_type(dtypes) == exp_type


def test_datetimetz_dtype_match():
    dtype = DatetimeTZDtype(unit="ns", tz="US/Eastern")
    assert find_common_type([dtype, dtype]) == "datetime64[ns, US/Eastern]"


@pytest.mark.parametrize(
    "dtype2",
    [
        DatetimeTZDtype(unit="ns", tz="Asia/Tokyo"),
        np.dtype("datetime64[ns]"),
        object,
        np.int64,
    ],
)
def test_datetimetz_dtype_mismatch(dtype2):
    dtype = DatetimeTZDtype(unit="ns", tz="US/Eastern")
    assert find_common_type([dtype, dtype2]) == object
    assert find_common_type([dtype2, dtype]) == object


def test_period_dtype_match():
    dtype = PeriodDtype(freq="D")
    assert find_common_type([dtype, dtype]) == "period[D]"


@pytest.mark.parametrize(
    "dtype2",
    [
        DatetimeTZDtype(unit="ns", tz="Asia/Tokyo"),
        PeriodDtype(freq="2D"),
        PeriodDtype(freq="h"),
        np.dtype("datetime64[ns]"),
        object,
        np.int64,
    ],
)
def test_period_dtype_mismatch(dtype2):
    dtype = PeriodDtype(freq="D")
    assert find_common_type([dtype, dtype2]) == object
    assert find_common_type([dtype2, dtype]) == object


interval_dtypes = [
    IntervalDtype(np.int64, "right"),
    IntervalDtype(np.float64, "right"),
    IntervalDtype(np.uint64, "right"),
    IntervalDtype(DatetimeTZDtype(unit="ns", tz="US/Eastern"), "right"),
    IntervalDtype("M8[ns]", "right"),
    IntervalDtype("m8[ns]", "right"),
]


@pytest.mark.parametrize("left", interval_dtypes)
@pytest.mark.parametrize("right", interval_dtypes)
def test_interval_dtype(left, right):
    result = find_common_type([left, right])

    if left is right:
        assert result is left

    elif left.subtype.kind in ["i", "u", "f"]:
        # i.e. numeric
        if right.subtype.kind in ["i", "u", "f"]:
            # both numeric -> common numeric subtype
            expected = IntervalDtype(np.float64, "right")
            assert result == expected
        else:
            assert result == object

    else:
        assert result == object


@pytest.mark.parametrize("dtype", interval_dtypes)
def test_interval_dtype_with_categorical(dtype):
    obj = Index([], dtype=dtype)

    cat = Categorical([], categories=obj)

    result = find_common_type([dtype, cat.dtype])
    assert result == dtype
